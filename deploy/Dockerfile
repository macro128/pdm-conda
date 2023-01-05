ARG env="prod"
# dev/build stage
FROM mambaorg/micromamba:jammy AS dev

ARG MAMBA_DOCKERFILE_ACTIVATE=1

# install PDM
COPY ./deploy/env.yml .
RUN --mount=type=cache,target=/opt/conda/pkgs,id=mamba,mode=0775,uid=1000,gid=1000,sharing=locked \
    micromamba install -y -f env.yml -n base

RUN micromamba clean -y -a

COPY ./deploy/pdm_install.py .

ARG pyproject=pyproject.toml
ARG lockfile=pdm.lock
# install dependencies
COPY ${pyproject} pyproject.toml
COPY --chown=$MAMBA_USER ${lockfile}* pdm.lock

ARG env="prod"
ARG dependencies=""
RUN python pdm_install.py -G ${dependencies} - --${env} --no-editable --no-self -v

# prod stage
FROM mambaorg/micromamba:jammy AS prod

# get environment
COPY --from=dev /opt/conda /opt/conda

RUN micromamba remove -y pdm pdm-pep517 -n base && \
    micromamba clean -y -a

# prepare deploy path
ENV SRC_PATH=/app/src/
WORKDIR $SRC_PATH

# copy src
ARG src=./
COPY --chown=$MAMBA_USER $src $src

# runtime stage
FROM ${env} AS runtime

# add src to python path
ENV SRC_PATH=/app/src/
ENV PYTHONPATH $SRC_PATH:$PYTHONPATH
WORKDIR $SRC_PATH

ENTRYPOINT ["/usr/local/bin/_entrypoint.sh", "tini", "--"]
