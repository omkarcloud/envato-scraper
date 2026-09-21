FROM chetan1111/botasaurus:chrome-151

ENV PYTHONUNBUFFERED=1
# Never open debug prompts/devtools on crash.
ENV ENV=production

COPY requirements.txt .

RUN python -m pip install -r requirements.txt

RUN mkdir app
WORKDIR /app
COPY . /app

EXPOSE 8000

# The image ships real Google Chrome + Xvfb. Envato Elements is plain HTTP;
# Chrome starts on the first Envato Market request (Cloudflare) and closes
# again after 15 idle minutes.
CMD ["python", "run.py"]
