# ImGen Changelog

## v1.5.3

- **Fix**: `editimage`/`makeimage` no longer reject valid model/size/quality selections ("Invalid model selection", "Invalid size selection", "Invalid quality selection"). These options use autocomplete, which does not restrict input, so Discord can submit the display label ("GPT Image 2", "2160x3840 (4K Portrait)") or wrong casing ("High") instead of the canonical value. Submitted options are now normalized (exact value, case-insensitive, or label reverse-map) before validation.
