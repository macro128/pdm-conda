ARG env="prod"
ARG app_env="app"
ARG base="core"
ARG src="./src"
ARG src_path="/app/"
ARG project_type="lib"
# core stage with no extras
FROM mambaorg/micromamba:latest AS core

ARG MAMBA_DOCKERFILE_ACTIVATE=1
ARG tini_version="0.19.*"
ENV TZ="Etc/UTC"
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    micromamba install -y tini==${tini_version} python==3.10.* git -n base -c conda-forge --always-copy

ADD --chown=${MAMBA_USER} https://github.com/apache/httpd/raw/trunk/docs/conf/mime.types /etc/mime.types

RUN micromamba clean -a -y

# ssh access
FROM core AS ssh

ARG mamba_user_password="root"
USER root
RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,id=debconf,target=/var/cache/debconf,sharing=locked \
    apt update && \
    apt install -y openssh-server --no-install-recommends && \
    mkdir /var/run/sshd && \
    # change mamba user pass
    echo "${MAMBA_USER}:${mamba_user_password}" | chpasswd && \
    echo -e 'root\nroot' | passwd && \
    sed -i '/^exec /i echo "root" | su -c "service ssh start"' /usr/local/bin/_entrypoint.sh

RUN apt clean
USER ${MAMBA_USER}

# dev/build stage
FROM ${base} AS src-app

# install PDM and create app environment
ARG app_env
ARG python_version="3.10.*"
ARG pdm_version="2.16.1"
ENV BIN_PATH=/opt/conda/_bin
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    micromamba install -y pdm==${pdm_version} -n base -c conda-forge --always-copy && \
    micromamba create -y -n ${app_env} python==${python_version} -c conda-forge --always-copy && \
    mkdir ${BIN_PATH} && \
    ln -s /opt/conda/bin/git ${BIN_PATH}/git && \
    ln -s /opt/conda/envs/${app_env}/bin/python ${BIN_PATH}/python && \
    ln -s /opt/conda/bin/pdm ${BIN_PATH}/pdm

RUN micromamba clean -a -y

COPY ./scripts/pdm_install.py /tmp

ARG src_path
WORKDIR $src_path

# copy PDM conf files
ARG pyproject=pyproject.toml
COPY ${pyproject} pyproject.toml
COPY --chown=${MAMBA_USER} LICENSE* README.* ./

ENV ENV_NAME=${app_env} \
    PDM_CONDA_INSTALLATION_METHOD="copy" \
    PDM_CONDA_CUSTOM_BEHAVIOR=1 \
    PATH=${BIN_PATH}:${PATH}
# install plugins
RUN pdm install --plugins -v

FROM src-app AS src-lib

# copy sources
ARG src
COPY --chown=${MAMBA_USER} ${src} ${src}

FROM src-${project_type} AS dev

# copy lockfile
ARG lockfile=pdm.lock
COPY --chown=${MAMBA_USER} ${lockfile}* ./

# install dependencies and project
ARG env
ARG project_type
ARG dependencies=""
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    python /tmp/pdm_install.py -G ${dependencies} --${project_type} - --${env} -x --lockfile ${lockfile}
# add src to python path
ARG src_path
ARG src
ENV PYTHONPATH=${src_path}${src}:${PYTHONPATH}

RUN micromamba clean -a -y

# this stages are dummy only for allowing to choose them later
FROM dev AS dev-app

FROM dev AS dev-lib

# prod stage
FROM ${base} AS prod-lib

# get environment
ARG app_env
COPY --from=dev /opt/conda/envs/${app_env} /opt/conda/envs/${app_env}

FROM prod-lib AS prod-app

# get sources
ARG src
ARG src_path
COPY --from=src-lib ${src_path}${src} ${src_path}${src}
ENV PYTHONPATH=${src_path}${src}:${PYTHONPATH}

# runtime stage
FROM ${env}-${app_env} as final

ARG app_env
ARG local_path
ARG src_path
ARG src
ENV ENV_NAME=${app_env} \
    LOCAL_PATH=${local_path} \
    SRC_PATH="${src_path}${src}"
WORKDIR ${src_path}

ENTRYPOINT ["/usr/local/bin/_entrypoint.sh", "/opt/conda/bin/tini", "--"]
