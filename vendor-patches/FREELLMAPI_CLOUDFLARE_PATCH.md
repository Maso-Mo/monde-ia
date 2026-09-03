# FreeLLMAPI Cloudflare Object Content Patch

## Overview
This patch fixes an issue where Cloudflare (specifically the Qwen2.5-coder-32b-instruct model) returns a JSON object directly in `choices[0].message.content` instead of a string. FreeLLMAPI was converting this to an empty string, resulting in `empty_completion` errors.

## Upstream Reference
- **Version**: v0.9.4
- **Commit**: 619cae9
- **Date**: Applied on top of FreeLLMAPI main branch

## Root Cause
Cloudflare Workers AI can return structured JSON objects directly in the `content` field when using certain models (verified with `@cf/qwen/qwen2.5-coder-32b-instruct`, `finish_reason="stop"`):

```json
{
  "issues_found": [...],
  "severity": "critical",
  "instructions_for_fix": [...],
  "retry_needed": true
}
```

FreeLLMAPI's `normalizeOutboundContent` function only handled array content (converting to string via `contentToString`), but left non-array objects untouched. Since `contentToString` returns `""` for objects, the content became an empty string downstream.

## Solution
Modified `normalizeOutboundContent` in `server/src/lib/content.ts` to accept an optional `platform` parameter. When `platform === "cloudflare"`:

1. **Object content** → serialized with `JSON.stringify()`
2. **Null/undefined content** → converted to empty string `""` (matching `contentToString` behavior)
3. **Array content** → existing behavior preserved (converted via `contentToString`)
4. **String content** → existing behavior preserved (passed through)

Other providers retain their existing behavior (non-array content passes through unchanged).

## Files Changed
1. `server/src/lib/content.ts` - Core logic modification
2. `server/src/routes/proxy.ts` - Two call sites updated to pass `route.platform`:
   - Streaming path (~line 2202)
   - Non-streaming path (~line 2638)
3. `server/src/__tests__/lib/content.test.ts` - Added 10 regression tests

## Testing
All 44 content tests pass, including new regression tests covering:
- Cloudflare message.content object → JSON.stringify
- Cloudflare delta.content object → JSON.stringify (streaming)
- Cloudflare null/undefined content → empty string
- Non-Cloudflare providers + object → existing behavior (object passes through)
- No platform provided + object → existing behavior (object passes through)
- Cloudflare array content → existing behavior preserved
- Cloudflare string content → existing behavior preserved

## Docker Image
Built locally as: `zflm/freellmapi:v0.9.4-zflm1`

```bash
docker build -t zflm/freellmapi:v0.9.4-zflm1 \
  --build-arg FREELLMAPI_COMMIT_SHA=$(git rev-parse HEAD) .
```

## Patch Application
The patch file `freellmapi-cloudflare-object-content.patch` can be applied to a clean FreeLLMAPI v0.9.4 checkout:

```bash
git apply freellmapi-cloudflare-object-content.patch
```

## Notes
- No secrets in patch or documentation
- Targeted fix only affects Cloudflare platform
- Existing behavior for all other providers preserved
- No changes to request path (only response normalization)