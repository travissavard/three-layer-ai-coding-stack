#!/usr/bin/env bash
set -euo pipefail

uv_version="0.12.10"
uv_base_url="https://github.com/astral-sh/uv/releases/download/${uv_version}"
script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/three-layer-installer.XXXXXXXX")"

cleanup() {
  rm -rf -- "${temp_root}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export UV_CACHE_DIR="${temp_root}/cache"
export UV_PYTHON_INSTALL_DIR="${temp_root}/python"
export UV_PROJECT_ENVIRONMENT="${temp_root}/project-environment"

if command -v uv >/dev/null 2>&1; then
  uv_command="$(command -v uv)"
else
  os_name="$(uname -s)"
  architecture="$(uname -m)"
  case "${os_name}-${architecture}" in
    Darwin-x86_64)
      asset="uv-x86_64-apple-darwin.tar.gz"
      expected_hash="5296d5aa2b9143360405eea866f8ef4d5dc8986b164eb0dc35e8f876a9304d30"
      ;;
    Darwin-arm64|Darwin-aarch64)
      asset="uv-aarch64-apple-darwin.tar.gz"
      expected_hash="51c6170e8e3a01cef9f33b94f582b7b81ac65046f55d40afb35f9cff5a68c179"
      ;;
    Linux-x86_64|Linux-amd64)
      asset="uv-x86_64-unknown-linux-gnu.tar.gz"
      expected_hash="173d95a0c32d18c896c46ba6fafbf3cf9c14ab74b033f81b76c883ef492a976b"
      ;;
    Linux-aarch64|Linux-arm64)
      asset="uv-aarch64-unknown-linux-gnu.tar.gz"
      expected_hash="9ff6b9d4665edcdd3a88dcc73cd1eb641754deb927f14e8c62ebfde6bf4f5f5e"
      ;;
    *)
      echo "Unsupported platform: ${os_name}-${architecture}" >&2
      exit 3
      ;;
  esac

  archive="${temp_root}/${asset}"
  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --silent --show-error "${uv_base_url}/${asset}" --output "${archive}"
  elif command -v wget >/dev/null 2>&1; then
    wget --quiet "${uv_base_url}/${asset}" --output-document="${archive}"
  else
    echo "curl or wget is required to bootstrap uv" >&2
    exit 3
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    actual_hash="$(sha256sum "${archive}" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    actual_hash="$(shasum -a 256 "${archive}" | awk '{print $1}')"
  else
    echo "sha256sum or shasum is required to verify uv" >&2
    exit 3
  fi
  if [[ "${actual_hash}" != "${expected_hash}" ]]; then
    echo "uv archive checksum mismatch" >&2
    exit 6
  fi

  mkdir "${temp_root}/uv"
  tar -xzf "${archive}" -C "${temp_root}/uv"
  uv_command="$(find "${temp_root}/uv" -type f -name uv -print -quit)"
  if [[ -z "${uv_command}" ]]; then
    echo "Verified uv archive did not contain uv" >&2
    exit 6
  fi
  chmod +x "${uv_command}"
  export THREE_LAYER_BOOTSTRAP_UV_DIR
  THREE_LAYER_BOOTSTRAP_UV_DIR="$(dirname -- "${uv_command}")"
fi

"${uv_command}" run --frozen --no-dev --project "${script_dir}" python -m three_layer_installer "$@"
