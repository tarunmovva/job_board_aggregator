# URL Normalization Fix Summary

## Problem Identified
The original URL normalization was **too aggressive**, causing different job postings to be treated as identical:

```
❌ BEFORE (Overly Aggressive):
https://www.moveworks.com/us/en/company/careers/position?gh_jid=8153753002
https://www.moveworks.com/us/en/company/careers/position?gh_jid=8128924002
    ↓ (both normalized to)
https://www.moveworks.com/us/en/company/careers/position

Result: Different jobs treated as same job!
```

## Root Cause
- **Query Parameter Removal**: The old normalization removed `?gh_jid=XXXXX` parameters
- **Job ID Loss**: `gh_jid` (GitHub Job ID) is essential for distinguishing individual job postings
- **False Collisions**: Multiple unique jobs were mapped to the same normalized URL

## Solution Implemented
**Conservative normalization** that preserves job-identifying parameters:

```
✅ AFTER (Conservative):
https://www.moveworks.com/us/en/company/careers/position?gh_jid=8153753002
    ↓ (normalized to)
https://www.moveworks.com/us/en/company/careers/position?gh_jid=8153753002

https://www.moveworks.com/us/en/company/careers/position?gh_jid=8128924002  
    ↓ (normalized to)
https://www.moveworks.com/us/en/company/careers/position?gh_jid=8128924002

Result: Each job remains unique!
```

## New Normalization Rules
1. **✅ Keep**: All query parameters (especially `gh_jid`, `job_id`, etc.)
2. **✅ Keep**: All URL paths and domains  
3. **❌ Remove**: Only fragments (`#apply`, `#top`, etc.)
4. **❌ Remove**: Trailing slashes on directory paths (only when no query params)

## Code Changes Made

### Updated `_normalize_url()` method:
```python
def _normalize_url(self, url: str) -> str:
    """Normalize URL for consistent matching - only remove special characters that cause parsing issues."""
    if not url:
        return ""
    
    # Only basic cleanup - preserve job-specific parameters like gh_jid
    url = str(url).strip()
    
    # Remove fragments (# anchors) as they don't affect job identity
    if '#' in url:
        url = url.split('#')[0]
    
    # Keep all query parameters - they often contain job IDs
    # Don't remove ? parameters as they're essential for job identification
    
    # Only normalize trailing slash for paths that are clearly directories
    # (have no query params and end with /)
    if url.endswith('/') and '?' not in url and url.count('/') > 3:
        url = url[:-1]
    
    return url
```

## Impact

### Before Fix:
```
WARNING - Found 2 normalized URLs with multiple original forms:
WARNING -   'https://www.moveworks.com/us/en/company/careers/position' maps to both 
  'https://www.moveworks.com/us/en/company/careers/position?gh_jid=8153753002&gh_jid=8153753002' 
  and 'https://www.moveworks.com/us/en/company/careers/position?gh_jid=8128924002&gh_jid=8128924002'
```

### After Fix:
```
✅ No collision warnings
✅ Each job has unique normalized URL
✅ Job-specific parameters preserved
✅ AI models can properly distinguish between different jobs
```

## Verification
- ✅ **Moveworks jobs**: Now have unique normalized URLs (different `gh_jid` values preserved)
- ✅ **Elastic jobs**: Now have unique normalized URLs (different `gh_jid` values preserved)  
- ✅ **Fragment removal**: Still works (`#apply` removed from URLs)
- ✅ **Directory normalization**: Still works (trailing slashes removed appropriately)
- ✅ **Job identification**: Each job posting maintains its unique identity

## Result
The system now properly handles multiple job postings from the same company while maintaining the ability to normalize URLs for AI model consistency. Each job posting is treated as a unique entity, as it should be.