"""Utils for scraping"""

from asyncio import sleep
from base64 import b64decode
import os
from io import BytesIO
import typing
from pathlib import Path
from enum import Enum
import re
from PIL import Image, UnidentifiedImageError
import pytesseract  # type: ignore
from playwright.async_api import async_playwright, Page, TimeoutError

LAW = "https://services.ecourts.gov.in/ecourtindia_v6/?p=cause_list/"

IMG_TO_CANVAS_JS = """() => {
        const img = document.querySelector("img#captcha_image");
        if (!img) throw new Error("Image not found");

        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        ctx.drawImage(img, 0, 0);

        return canvas.toDataURL("image/png");
    }
"""

CAPTCHA = "img#captcha_image"
CLOSE = "div.modal-header.text-center.align-items-start button.btn-close"

CNR_NUMBER = "span.fw-bold.text-uppercase.fs-5.me-2.text-danger"

STATE = "#sess_state_code"
DIST = "#sess_dist_code"
COURT = "#court_complex_code"
COURT_NAME = "#CL_court_no"
DATE = "#causelist_date"
CAPTCHA_CODE = "#cause_list_captcha_code"
REFRESH = "img.refresh-btn"
CIVIL = "button:has-text('Civil')"
CRIMINAL = "button:has-text('Criminal')"

VIEW = "a.someclass"
BACK = "button#main_back_CauseList"

MAX_FETCH = 5
MAX_ITERATIONS = 10


class CaseType(Enum):
    """Simple enum for case type"""

    CIVIL = CIVIL
    CRIMINAL = CRIMINAL


class Dict(typing.NamedTuple):
    cnr: str
    path: str


class WebScraper:
    """Base class to transfer context"""

    PATH: str
    """ Default Path"""
    HEADLESS: bool
    """ Toggle Headless mode"""

    def __init__(self, path: str, headless: bool = True):
        self.PATH = path
        self.HEADLESS = headless

    @staticmethod
    async def solve_captcha(page: Page) -> str:
        """Try to allow the captcha"""
        try:
            image = Image.open(await WebScraper.download_image(page))
            return pytesseract.image_to_string(image, lang="eng")
        except UnidentifiedImageError:
            print("[ERROR]: Invalid Image format found")
            return ""

    @staticmethod
    async def download_image(page: Page):
        """Download the image without fetching it"""
        data_url: str = await page.evaluate(IMG_TO_CANVAS_JS)
        base64_data = data_url.split(",")[1]
        byte = BytesIO()
        byte.write(b64decode(base64_data))
        return byte

    @staticmethod
    async def choose_option(page: Page, parent: str, name: str) -> None:
        """Choose a option based on innerText"""

        parent_node = page.locator(parent)
        option = page.locator(f"{parent} option")
        await parent_node.click()
        opt = option.get_by_text(re.compile(name, re.IGNORECASE))
        value = await opt.get_attribute("value")
        await parent_node.select_option(value)

    @staticmethod
    async def choose_state(page: Page, name: str) -> None:
        """Choose a option based on innerText for state"""
        try:
            await WebScraper.choose_option(page, STATE, name)
        except TimeoutError:
            print(f"[ERROR]: Failed to find option {name} for State")

    @staticmethod
    async def choose_district(page: Page, name: str) -> None:
        """Choose a option based on innerText"""

        try:
            await WebScraper.choose_option(page, DIST, name)
        except TimeoutError:
            print(f"[ERROR]: Failed to find option {name} for District")

    @staticmethod
    async def choose_complex(page: Page, name: str) -> None:
        """Choose a option based on innerText"""

        try:
            await WebScraper.choose_option(page, COURT, name)
        except TimeoutError:
            print(f"[ERROR]: Failed to find option {name} for Court Complex")

    @staticmethod
    async def choose_name(page: Page, name: str) -> None:
        """Choose a option based on innerText"""

        try:
            await WebScraper.choose_option(page, COURT_NAME, name)
        except TimeoutError:
            print(f"[ERROR]: Failed to find option {name} for Court Name")

    @staticmethod
    async def fill_value(page: Page, node: str, value: str) -> None:
        """Enter value into a input node"""
        try:
            input_form = page.locator(node)
            await input_form.fill("")
            await input_form.fill(value)
        except TimeoutError:
            print("[ERROR]: Failed to fill input")

    @staticmethod
    async def get_all_options(page: Page, node: str):
        """Get all option value and innerText"""
        loc: list[str] = []
        select = page.locator(f"{node} option")
        await sleep(5)
        options = await select.all()

        for i in options:
            value = await i.get_attribute("value") or ""
            text = await i.inner_text()
            disabled = await i.get_attribute("disabled")

            if value and disabled is None:
                loc.append(text)

        return loc

    async def get_pdfs(
        self, page: Page, state: str, dist: str, court: str, court_name: str
    ):
        """Get all pdfs available on page"""

        back = page.locator(BACK)
        view = page.locator(VIEW)
        await sleep(5)
        records = await view.all()

        parent = Path(self.PATH).joinpath(state, dist, court, court_name)
        try:
            if records:
                os.makedirs(parent, exist_ok=True)

                for record in records:
                    await record.click()
                    await sleep(5)
                    name = await page.locator(CNR_NUMBER).first.inner_text()
                    await page.pdf(path=parent.joinpath(f"{name}.pdf").absolute())
                    await sleep(5)
                    await back.click()
                    await page.wait_for_load_state("networkidle")

                    yield Dict(name, str(parent.joinpath(f"{name}.pdf")))
        except TimeoutError:
            print(
                f"[ERROR]: Failed to download pdf for State {state} - District {dist} - Court Complex {court} - Court name {court_name}"
            )

    @staticmethod
    async def pass_captcha(page: Page, case_type: CaseType):
        """Solve the captcha"""
        close = page.locator(CLOSE)
        idx = 0

        while (
            await close.first.is_visible() and idx < MAX_ITERATIONS
        ):  # keep solving captcha
            await close.first.click()
            await page.locator(REFRESH).click()
            await sleep(2)
            await WebScraper.fill_value(
                page, CAPTCHA_CODE, await WebScraper.solve_captcha(page)
            )
            await page.locator(case_type.value).click()
            await sleep(2)
            idx += 1
        if idx == MAX_ITERATIONS:
            raise ValueError("Failed to solve captcha. Please try again")

    async def begin_scrape(
        self,
        chosen_state: str,
        chosen_dist: str,
        chosen_court: str,
        chosen_court_name: str,
        chosen_date: str,
        case_type: CaseType,
    ) -> typing.AsyncGenerator[Dict, None]:
        """Scrape for one court name"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            page = await browser.new_page()
            await page.goto(LAW, timeout=0)

            # Wait for page to load properly
            await page.wait_for_load_state("networkidle")
            await sleep(5)

            close = page.locator(CLOSE)

            if await close.first.is_visible():
                await close.first.click()

            await WebScraper.choose_state(page, chosen_state)
            await WebScraper.choose_district(page, chosen_dist)
            await WebScraper.choose_complex(page, chosen_court)
            await WebScraper.choose_name(page, chosen_court_name)
            await page.locator(DATE).fill(chosen_date)
            await WebScraper.fill_value(page, DATE, chosen_date)

            await WebScraper.fill_value(
                page, CAPTCHA_CODE, await WebScraper.solve_captcha(page)
            )
            await page.locator(case_type.value).click()

            await WebScraper.pass_captcha(page, case_type)

            async for i in self.get_pdfs(
                page, chosen_state, chosen_dist, chosen_court, chosen_court_name
            ):
                yield i

    async def begin_scrape_all(
        self,
        chosen_state: str,
        chosen_dist: str,
        chosen_court: str,
        chosen_date: str,
        case_type: CaseType,
    ) -> typing.AsyncGenerator[Dict, None]:
        """Scrape for one court name"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            page = await browser.new_page()
            await page.goto(LAW, timeout=0)

            # Wait for page to load properly
            await page.wait_for_load_state("networkidle")
            await sleep(5)

            close = page.locator(CLOSE)

            if await close.first.is_visible():
                await close.first.click()

            await WebScraper.choose_state(page, chosen_state)
            await WebScraper.choose_district(page, chosen_dist)
            await WebScraper.choose_complex(page, chosen_court)

            court_names = await WebScraper.get_all_options(page, COURT_NAME)

            for name in court_names:
                if await close.first.is_visible():
                    await close.first.click()

                await WebScraper.choose_name(page, name)

                await page.locator(DATE).fill(chosen_date)
                await WebScraper.fill_value(page, DATE, chosen_date)

                await WebScraper.fill_value(
                    page, CAPTCHA_CODE, await WebScraper.solve_captcha(page)
                )
                await page.locator(case_type.value).click()

                await WebScraper.pass_captcha(page, case_type)
                await sleep(3)

                async for i in self.get_pdfs(
                    page, chosen_state, chosen_dist, chosen_court, name
                ):
                    yield i
