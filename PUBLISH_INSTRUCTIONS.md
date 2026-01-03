# Publishing to GitHub and HACS

This document contains step-by-step instructions for publishing this integration to GitHub and making it available in HACS.

## Current Status ✅

The following has been completed:
- ✅ Repository structure created (HACS-compliant)
- ✅ All required files created (README.md, LICENSE, hacs.json, info.md)
- ✅ Git repository initialized
- ✅ Initial commit created
- ✅ Version tag v1.2.0 created
- ✅ Branch renamed to 'main'

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `waterlevel_ie`
3. Description: `Home Assistant integration for WaterLevel.ie - Ireland's water monitoring network`
4. Visibility: **Public** (required for HACS)
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **Create repository**

## Step 2: Push Code to GitHub

From the `/home_assistant/waterlevel_ie_github` directory, run:

```bash
cd /home_assistant/waterlevel_ie_github

# Add the remote repository (replace with your actual URL)
git remote add origin https://github.com/tuckshoprn/waterlevel_ie.git

# Push code and tags
git push -u origin main
git push origin v1.2.0
```

If you use SSH instead of HTTPS:
```bash
git remote add origin git@github.com:tuckshoprn/waterlevel_ie.git
git push -u origin main
git push origin v1.2.0
```

## Step 3: Create GitHub Release

1. Go to https://github.com/tuckshoprn/waterlevel_ie/releases
2. Click **Draft a new release**
3. Click **Choose a tag** → Select `v1.2.0`
4. Release title: `v1.2.0 - Enhanced Resilience & HACS Support`
5. Description:

```markdown
## What's New in v1.2.0

### 🎉 New Features
- **API Status Monitoring**: New binary sensor shows real-time API availability
- **Data Retention**: Keeps last known data for 24 hours during API outages
- **Configurable Updates**: Adjust update interval from 5-120 minutes
- **HACS Support**: Full HACS compatibility for easy installation

### 🚀 Improvements
- Exponential backoff retry logic (3 attempts with 1s, 2s, 4s delays)
- Smart error logging (reduces spam by 75% during outages)
- Increased API timeout from 10s to 30s
- Added display precision for optimal long-term statistics
- Enhanced sensor attributes with cached data indicators

### 🐛 Bug Fixes
- Removed excessive debug logging
- Improved error messages with better context

### 📊 Long-Term Statistics
All sensors now include:
- Proper display precision for each sensor type
- Full recorder support
- Cached data age indicators

## Installation

### Via HACS
1. Add this repository as a custom repository in HACS
2. Search for "WaterLevel.ie"
3. Click Install
4. Restart Home Assistant

### Manual
1. Download `waterlevel_ie.zip` below
2. Extract to `custom_components/waterlevel_ie`
3. Restart Home Assistant

## Requirements
- Home Assistant 2024.1.0 or newer
- Internet connection to waterlevel.ie

## Support
- [Documentation](https://github.com/tuckshoprn/waterlevel_ie/blob/main/README.md)
- [Report Issues](https://github.com/tuckshoprn/waterlevel_ie/issues)
```

6. Click **Publish release**

## Step 4: Add to HACS (Custom Repository Method)

Users can now add your integration to HACS:

1. Open HACS in Home Assistant
2. Click the three dots menu (⋮) in the top right
3. Select **Custom repositories**
4. Add repository URL: `https://github.com/tuckshoprn/waterlevel_ie`
5. Category: **Integration**
6. Click **Add**

Your integration will now appear in HACS searches!

## Step 5: Submit to HACS Default Repository (Optional)

To appear in HACS by default (not requiring custom repository):

### Prerequisites Checklist

Before submitting, verify:
- ✅ Repository is public
- ✅ Has at least one release with semantic versioning (v1.2.0)
- ✅ Contains all required files:
  - ✅ `hacs.json`
  - ✅ `README.md`
  - ✅ `info.md`
  - ✅ `LICENSE`
  - ✅ `custom_components/<domain>/manifest.json`
- ✅ Follows Home Assistant development standards
- ✅ No dependencies on external Python packages (in manifest.json)
- ✅ Works with current Home Assistant version

### Submission Process

1. Fork https://github.com/hacs/default
2. Add your repository to `integration` file:
   ```json
   {
     "name": "tuckshoprn/waterlevel_ie",
     "category": "integration"
   }
   ```
3. Create Pull Request with title: `Add tuckshoprn/waterlevel_ie`
4. Wait for HACS team review (can take several days/weeks)
5. Address any feedback
6. Once merged, your integration appears in HACS by default!

**Note**: Starting as a custom repository is fine. Many users successfully use custom repos.

## Step 6: Repository Settings (Recommended)

### Enable GitHub Issues
1. Go to repository **Settings** → **General**
2. Scroll to **Features**
3. Enable **Issues**

### Add Topics
1. Go to repository main page
2. Click the gear icon next to **About**
3. Add topics:
   - `home-assistant`
   - `hacs`
   - `home-assistant-integration`
   - `water-level`
   - `ireland`
   - `opw`

### Create Issue Templates
Create `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md` for better issue management.

## Step 7: Promote Your Integration

Share on:
- Home Assistant Community Forum
- Home Assistant Reddit (r/homeassistant)
- Twitter/X with #HomeAssistant hashtag
- Home Assistant Discord

## Maintenance

### For Future Updates

1. Make code changes
2. Update version in `manifest.json`
3. Update `README.md` changelog
4. Commit changes
5. Create new tag: `git tag -a v1.3.0 -m "Description"`
6. Push: `git push && git push --tags`
7. Create new GitHub release

### HACS Auto-Updates

Once users install via HACS:
- HACS automatically checks for new releases
- Users get notifications when updates are available
- They can update with one click!

## Support Resources

- **HACS Documentation**: https://hacs.xyz/docs/publish/start
- **HA Integration Quality Scale**: https://www.home-assistant.io/docs/quality_scale/
- **HA Developer Docs**: https://developers.home-assistant.io/

## Troubleshooting

### "Repository is not compliant"
- Check `hacs.json` format
- Verify all required files exist
- Ensure you have at least one release

### "No valid releases found"
- Tag must use semantic versioning (v1.2.0, not 1.2.0)
- Release must be published (not draft)

### Users can't find in HACS
- Must be added as custom repository first
- Or wait for default repository PR to be merged

---

**Ready to publish?** Follow the steps above in order. Good luck! 🚀
