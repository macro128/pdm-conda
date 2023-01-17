ARG env="prod"
ARG app_env="app"
ARG src=./
ARG python_version="3.10.*"
# dev/build stage
FROM mambaorg/micromamba:jammy AS dev

ARG MAMBA_DOCKERFILE_ACTIVATE=1

# install PDM and create app environment
ARG app_env
ARG python_version
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    micromamba install -y python==3.10.* pdm==2.4.* pdm-pep517==1.0.* tini==0.19.* -n base -c conda-forge && \
    micromamba create -y -n ${app_env} python==${python_version} -c conda-forge

RUN micromamba clean -y -a

COPY ./deploy/pdm_install.py /tmp

ENV SRC_PATH=/app/src/
WORKDIR $SRC_PATH

# copy PDM conf files
ARG pyproject=pyproject.toml
COPY ${pyproject} pyproject.toml
ARG lockfile=pdm.lock
COPY --chown=${MAMBA_USER} ${lockfile}* pdm.lock
COPY LICENSE* README.* ./

# copy sources
ARG src
COPY --chown=$MAMBA_USER $src $src

# install dependencies and project
ARG env
ARG dependencies=""
ENV ENV_NAME=${app_env}
RUN python /tmp/pdm_install.py "/opt/conda/bin/pdm" -G ${dependencies} - --${env}
# add src to python path
ENV PYTHONPATH ${SRC_PATH}:${PYTHONPATH}

# prod stage
FROM mambaorg/micromamba:jammy AS prod

# get environment
COPY --from=dev /opt/conda /opt/conda

RUN micromamba remove -y python pdm pdm-pep517 -n base && \
    micromamba clean -y -a

# runtime stage
FROM ${env} AS runtime

# add src to python path
ENV SRC_PATH=/app/src/
WORKDIR ${SRC_PATH}

ARG app_env
ENV ENV_NAME=${app_env}
ENTRYPOINT ["/usr/local/bin/_entrypoint.sh", "/opt/conda/bin/tini", "--"]
