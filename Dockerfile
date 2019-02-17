FROM py37


RUN mkdir -p /opt/f5go

COPY ./etc/motd /root/
RUN echo "cat /root/motd" >> /root/.bashrc

#COPY ./src/* /opt/f5go/
WORKDIR /opt/f5go

COPY ./etc/pylintrc /opt/f5go

RUN pip install --upgrade pip
RUN pip install pip-tools
COPY ./src/requirements.in /opt/f5go
RUN pip-compile --output-file requirements.txt requirements.in
RUN pip install -r requirements.txt

# catch anything which would stop python at runtime
# RUN pylint --errors-only go.py core.py tools.py

CMD /bin/bash
ENTRYPOINT []