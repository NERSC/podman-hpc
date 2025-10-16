FROM python:3.14-alpine
LABEL maintainer="scanon@lbl.gov"

RUN pip3 install ldap3

WORKDIR /subxid
ADD subxid/* .

ENTRYPOINT [ "./entrypoint.sh" ]

