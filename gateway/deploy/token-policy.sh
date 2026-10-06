#!/usr/bin/env bash

raise_gateway_token_is_valid() {
  local value="${1-}"

  if [ "${#value}" -lt 32 ]; then
    return 1
  fi

  if [[ "$value" =~ [[:space:][:cntrl:]] ]]; then
    return 1
  fi

  return 0
}
