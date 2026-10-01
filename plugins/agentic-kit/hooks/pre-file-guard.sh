#!/usr/bin/env bash
set -uo pipefail
# Resolve the library relative to this script, not ${CLAUDE_PLUGIN_ROOT}: under
# `set -u` an unset variable would error before the inertness check could run.
# Pure parameter expansion, no `dirname`: PATH may hold nothing at all.
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init
exit 0
