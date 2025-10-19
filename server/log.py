""" Logging Module """
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

file_path = Path(Path(__file__).parent, "logs", "app.log")
console, file = (
    logging.StreamHandler(),
    logging.FileHandler(file_path, mode="a", encoding="utf-8"),
)
formatter = logging.Formatter(
    "[{asctime}]:[{levelname}]:{message}", style="{", datefmt="%d-%m-%Y %H:%M"
)
console.setFormatter(formatter)
file.setFormatter(formatter)
logger.addHandler(console)
logger.addHandler(file)
logger.setLevel(logging.DEBUG)
