#!/usr/bin/env bash
# PostToolUse/Edit,Write. Runs the project formatter on the edited file.
# Never blocks: a formatter failure is a formatting problem, not a policy breach.
# Every path out of this script is `exit 0`, and the formatter is silenced.
set -uo pipefail
# Resolve the library relative to this script, not ${CLAUDE_PLUGIN_ROOT}: under
# `set -u` an unset variable would error before the inertness check could run.
# Pure parameter expansion, no `dirname`: PATH may hold nothing at all.
_kit_dir="${BASH_SOURCE[0]%/*}"; [ "$_kit_dir" != "${BASH_SOURCE[0]}" ] || _kit_dir=.
# shellcheck source=lib/kitlock.sh
source "$_kit_dir/lib/kitlock.sh" || exit 0
kit_init

path=$(kit_in '.tool_input.file_path')
[ -n "$path" ] || exit 0

# Source files only. A formatter configured for one language would mangle or
# reject the rest, and widening this list is a decision, not a default.
case "$path" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs|*.rb|*.java|*.kt|*.css|*.scss) ;;
  *) exit 0 ;;
esac

fmt=$(kit_q '.toolchain.format')
[ -n "$fmt" ] || exit 0

# The command is a configured string, split on purpose into words; globbing is
# switched off so a "*" in it cannot expand against the working directory.
set -f
# shellcheck disable=SC2086
timeout 30 $fmt "$path" >/dev/null 2>&1 || true
exit 0
