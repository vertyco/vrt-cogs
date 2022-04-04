from yarl import URL

DEFAULT_SCOPES = ["Xboxlive.signin", "Xboxlive.offline_access"]

query_string = {
  "client_id": "eb744d7c-0460-4bd7-8c6d-842db3517e0a",
  "response_type": "code",
  "approval_prompt": "auto",
  "scope": " ".join(DEFAULT_SCOPES),
  "redirect_uri": "http://localhost/auth/callback",
}

print(URL("https://login.windows-ppe.net/consumers/oauth2/v2.0/authorize").with_query(query_string))