# Container image that runs your code
FROM opensuse/leap:15.4

RUN zypper update -y \
 && zypper install -y \
     python3-pip \
     rpm-build \
     tar \
     make \
 && zypper clean

RUN pip install --upgrade build

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/entrypoint.sh"]
