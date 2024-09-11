FROM python:3.12-alpine

ENV PYTHON_VERSION=3.12
ARG USERNAME=user
ARG USER_UID=1000
ARG USER_GID=$USER_UID

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN mkdir /usr/src/app

RUN addgroup -g $USER_GID $USERNAME \
    && adduser -u $USER_UID -G $USERNAME -h /home/$USERNAME -D $USERNAME

RUN chown -R ${USER_UID}:${USER_GID} /usr/src/app

USER user
RUN pip install --user uv

WORKDIR /usr/src/app
RUN python -m uv venv --seed --python ${PYTHON_VERSION} .venv

RUN . .venv/bin/activate && python -m pip install uv
RUN --mount=type=cache,target=/home/${USERNAME}/.cache/uv,uid=${USER_UID},gid=${USER_GID} \
    --mount=type=bind,source=web/requirements.txt,target=requirements.txt \
    . .venv/bin/activate && python -m uv pip sync requirements.txt

COPY --chown=$USER_UID:$USER_GID web/ /usr/src/app/src/

ENTRYPOINT ["/bin/sh", "-c", "WEB_SERVER_EXTERNAL_IP=`awk 'END{print $1}' /etc/hosts` /usr/src/app/.venv/bin/python src/server.py"]
