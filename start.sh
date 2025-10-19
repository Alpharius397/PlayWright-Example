#usr/bin/bash

pip install -r require.txt
playwright install --with-deps chromium

cd server && fastapi dev main.py
