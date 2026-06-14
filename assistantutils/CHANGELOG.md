# AssistantUtils Changelog

## v1.10.0

- **New**: `fetch_channel_history` can now surface image attachments (screenshots) to vision models and inline the contents of attached text files (json, txt, csv, yaml, log, etc.). Added `include_images` and `include_text_attachments` params (both default true), so the model can opt out when it only needs text.
