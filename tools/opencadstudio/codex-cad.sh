#!/bin/sh
# Local OpenCADStudio agent. Never execute Codex with root privileges.
set -eu
if [ "$(id -u)" -eq 0 ]; then
  usercmd='/usr/sbin/runuser -u ocstest -- /usr/bin/env HOME=/home/ocstest'
elif [ "$(id -un)" = ocstest ]; then
  usercmd='/usr/bin/env HOME=/home/ocstest'
else
  echo 'Only root (drops to ocstest) or ocstest may run this command' >&2
  exit 77
fi
case "${1:-}" in
 exec|e)
   shift
   # The approved review path is needed for OpenCADStudio MCP mutations.
   # It does not bypass approval/sandbox protections.
   exec $usercmd /usr/bin/codex exec --approve-for-me --skip-git-repo-check -C /home/ocstest/opencadstudio "$@"
   ;;
 *)
   exec $usercmd /usr/bin/codex -C /home/ocstest/opencadstudio -s workspace-write "$@"
   ;;
esac