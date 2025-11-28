FROM python:3.12 

WORKDIR /backend

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . . 

ENV PORT=8000

CMD [ "gunicorn", "feedback.wsgi:application", "--bind", "0.0.0.0:8000" ]