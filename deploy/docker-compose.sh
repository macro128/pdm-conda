DEV=false
COMMAND=''
while [[ $# -gt 0 ]]; do
  case "$1" in
  --dev | -d)
    DEV=true
    ;;
  *)
    COMMAND=$*
    shift $(($# - 1))
    ;;
  esac
  shift
done

ENV_FILE="$PWD"/.env
ENV_FILE_DEST="$PWD"/deploy/.env
if [[ -f "$ENV_FILE" ]] && [[ ! -f "$ENV_FILE_DEST" ]]; then
  ln -s "$ENV_FILE" "$ENV_FILE_DEST"
fi

OPTS=""
if $DEV; then
  OPTS="-f deploy/docker-compose.dev.yaml"
  UID_GID="$(id -u):$(id -g)"
  export UID_GID
fi

if [[ "$COMMAND" == run* ]] && [[ "$COMMAND" != run*--rm* ]]; then
  readarray -td ' ' _COMMAND <<<"$COMMAND"
  COMMAND="${_COMMAND[0]} --rm "
  unset "_COMMAND[0]"
  COMMAND+="${_COMMAND[*]}"
fi

docker compose -f deploy/docker-compose.yaml $OPTS $COMMAND
