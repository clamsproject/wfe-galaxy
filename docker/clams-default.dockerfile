FROM clams-base

ADD . /app 
RUN [ -f /app/requirements.txt ] && pip install --user -r /app/requirements.txt

CMD python /app/app.py
