const errorMessages = {
  "native_unavailable": "Install the extension in Aside and connect the local helper.",
  "native_timeout": "The local helper did not respond. Refresh its status before retrying.",
  "native_connection": "Could not connect to the local helper. Follow the setup guide, then check again.",
  "invalid_response": "The helper response is invalid. Check its version.",
  "configuration": "The helper configuration is invalid. Review the installation settings.",
  "not_configured": "Set up the local helper before enabling Jev.",
  "key_missing": "Configure a TypeSafe API key on the host before enabling Jev.",
  "key_file": "Check the key file. Only simple TYPESAFE_API_KEY or TYPESAFEAI_API_KEY assignments are supported.",
  "busy": "Another update is running. Wait, then refresh the status.",
  "encoding": "A configuration file is not valid UTF-8. Check the original file.",
  "file_access": "Cannot access a required file. Check the installation paths and permissions.",
  "file_changed": "A file changed during the update. Review it and refresh the status.",
  "file_size": "A configuration file exceeds the size limit. Review the file before retrying.",
  "input": "Minimum confidence must be 0–1 and the HTTP timeout must be 1–60 seconds.",
  "installation_conflict": "A different installation already owns this connection. Review the existing registration.",
  "managed_block": "The managed instruction markers are damaged. Check the original file and its backup.",
  "origin": "This extension ID does not match the registered helper. Review the installation.",
  "profile_missing": "The selected Aside profile is missing. Review the installation path.",
  "rollback_failed": "The update could not be restored completely. Inspect the profile and backup before continuing.",
  "skill_conflict": "An existing skill is not managed by this extension. Review it before changing the installation.",
  "unsafe_path": "A path is not safe to update. Use the original profile directory and regular files.",
  "write_failed": "The update failed and was rolled back. Check permissions and refresh the status.",
  "message_size": "The helper message exceeds the size limit. Check the helper version.",
  "operation": "The helper does not support this request. Check the helper version.",
  "protocol": "The helper message could not be read. Check the helper version.",
  "internal": "The helper could not process this request. Check the installation paths and permissions."
};
export function errorText(code, original, t) {
  if (Object.hasOwn(errorMessages, code)) return t(errorMessages[code]);
  return t("Backend detail (original): {detail}", { detail: original || "Unknown helper error" });
}
export function warningText(status, t) {
  return status?.warnings?.length ? t("Global instructions need attention. OFF only affects this profile; global files were not changed.") : "";
}
