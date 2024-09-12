# hadolint global ignore=DL3042,SC1091
FROM python:3.12-slim

ENV PYTHON_VERSION=3.12
ARG USERNAME=user
ARG USER_UID=1000
ARG USER_GID=$USER_UID

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_VERSION=0.4.9

RUN mkdir /usr/src/app

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

RUN chown -R ${USER_UID}:${USER_GID} /usr/src/app

USER user
RUN pip install --user uv=="${UV_VERSION}"

WORKDIR /usr/src/app
RUN python -m uv python install ${PYTHON_VERSION} && \
    python -m uv venv --seed --python ${PYTHON_VERSION} .venv
RUN . .venv/bin/activate && python -m pip install uv=="${UV_VERSION}"
RUN --mount=type=cache,target=/home/${USERNAME}/.cache/uv,uid=${USER_UID},gid=${USER_GID} \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    . .venv/bin/activate && python -m uv pip sync requirements.txt

COPY --chown=$USER_UID:$USER_GID src/ /usr/src/app/src/
COPY --chown=$USER_UID:$USER_GID run.py /usr/src/app/run.py

ENTRYPOINT ["/bin/sh", "-c", "PYTHON_RANDOM_SEED=`shuf -i 0-65000 -n 1` /usr/src/app/.venv/bin/python run.py"]
