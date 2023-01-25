ARG env="prod"
ARG app_env="app"
ARG src=./
ARG src_path="/app/src/"
# dev/build stage
FROM mambaorg/micromamba:jammy AS dev

ARG MAMBA_DOCKERFILE_ACTIVATE=1

# install PDM and create app environment
ARG app_env
ARG python_version="3.10.*"
ARG pdm_version="2.4.*"
ENV BIN_PATH=/opt/conda/bin_
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    micromamba install -y python==3.10.* pdm==${pdm_version} git -n base -c conda-forge && \
    micromamba create -y -n ${app_env} python==${python_version} -c conda-forge && \
    mkdir ${BIN_PATH} && \
    ln -s /opt/conda/bin/git ${BIN_PATH}/git

RUN micromamba clean -a -y

COPY ./deploy/pdm_install.py /tmp

ARG src_path
WORKDIR $src_path

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
ARG plugins=""
ENV ENV_NAME=${app_env}
ENV CONDA_INSTALLATION_METHOD="copy"
ENV PATH=${BIN_PATH}:${PATH}
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    python /tmp/pdm_install.py "/opt/conda/bin/pdm" -G ${dependencies} --plugins pdm-backend ${plugins} - --${env}
# add src to python path
ENV PYTHONPATH=${src_path}:${PYTHONPATH}

# prod stage
FROM mambaorg/micromamba:jammy AS prod

# get environment
ARG app_env
COPY --from=dev /opt/conda/envs/$app_env /opt/conda/envs/$app_env

# runtime stage
FROM ${env} AS runtime

ARG tini_version="0.19.*"
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    micromamba install -y tini==${tini_version} -n base -c conda-forge

RUN micromamba clean -a -y

# add src to python path
ARG src_path
WORKDIR ${src_path}

ARG app_env
ENV ENV_NAME=${app_env}
ENTRYPOINT ["/usr/local/bin/_entrypoint.sh", "/opt/conda/bin/tini", "--"]
