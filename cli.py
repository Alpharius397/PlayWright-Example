"""CLI System"""

import datetime
import argparse
import asyncio
import typing
from utils import WebScraper, CaseType, Dict


class DateAction(argparse.Action):
    """Action to validate date"""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        try:
            assert isinstance(values, str), "Date must be a string"
            day, month, year = values.split("-")
            datetime.date.fromisoformat(f"{year}-{month}-{day}")
            setattr(namespace, self.dest, values)

        except (ValueError, AssertionError) as e:
            raise ValueError(f"Date must be in format: DD-MM-YYYY, Got: {values}") from e


parser = argparse.ArgumentParser()
parser.add_argument("--state", type=str, help="State Name", required=True)
parser.add_argument("--district", type=str, help="District Name", required=True)
parser.add_argument("--complex", type=str, help="Court Complex Name", required=True)
parser.add_argument(
    "--case", type=str, help="Case Type", required=True, choices=["Civil", "Criminal"]
)
parser.add_argument("--path", help="Path to store extracted pdfs", required=True)
parser.add_argument("-n", "--name", help="Court Name")
parser.add_argument(
    "-d",
    "--date",
    help="Cause List Date (Format: DD-MM-YYYY)",
    action=DateAction,
    required=True,
)
parser.add_argument(
    "-a", "--all", help="Fetch all court name", action="store_const", const=True
)
parser.add_argument(
    "--verbose", help="View scraping actions", action="store_false", default=True
)

args = parser.parse_args()

if args.all and args.name:
    raise ValueError("Both -a and -n both cannot be set")

if (not args.all) and (args.name is None):
    raise ValueError("Both -a and -n both cannot be unset")

caseType: CaseType = CaseType.CRIMINAL if args.case == "Criminal" else CaseType.CIVIL

web = WebScraper(args.path, bool(args.verbose))


async def main() -> None:
    """Entrypoint for async"""
    task: typing.AsyncGenerator[Dict, None] | None = None

    if args.all:
        task = web.begin_scrape_all(
            args.state, args.district, args.complex, args.date, caseType
        )
    else:
        task = web.begin_scrape(
            args.state, args.district, args.complex, args.name, args.date, caseType
        )

    async def __main__():
        async for cnr, path in task:
            print(f"[SUCCESS]: Saved CNR '{cnr}' to {path}")

    await __main__()


asyncio.run(main())
