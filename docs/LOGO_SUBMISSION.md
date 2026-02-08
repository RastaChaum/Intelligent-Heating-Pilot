# Logo Submission Guide for Home Assistant Integrations Page

This guide explains how to make the Intelligent Heating Pilot logo appear on the Home Assistant Integrations page.

## Background

Home Assistant displays integration logos by fetching them from the official [Home Assistant Brands repository](https://github.com/home-assistant/brands). Local logo files in the custom component directory are not displayed on the integrations page.

To have your logo displayed, you need to submit it to the Home Assistant Brands repository.

## Files Prepared

The following logo files have been prepared in `custom_components/intelligent_heating_pilot/`:

- ✅ `icon.png` - 256x256px square icon (required)
- ✅ `icon@2x.png` - 512x512px high-resolution icon (recommended)
- ✅ `logo.png` - Original logo (optional, fallback to icon if not provided)

These files meet the Home Assistant Brands repository requirements:
- PNG format
- Optimized for web
- Properly sized
- Transparent background
- Trimmed with minimal empty space

## Submission Process

### Step 1: Fork the Brands Repository

1. Go to [https://github.com/home-assistant/brands](https://github.com/home-assistant/brands)
2. Click the "Fork" button in the top right
3. Clone your fork to your local machine:
   ```bash
   git clone https://github.com/YOUR_USERNAME/brands.git
   cd brands
   ```

### Step 2: Create the Integration Folder

```bash
# Create folder for custom integration
mkdir -p custom_integrations/intelligent_heating_pilot

# Copy the prepared icon files
cp /path/to/Intelligent-Heating-Pilot/custom_components/intelligent_heating_pilot/icon.png \
   custom_integrations/intelligent_heating_pilot/
   
cp /path/to/Intelligent-Heating-Pilot/custom_components/intelligent_heating_pilot/icon@2x.png \
   custom_integrations/intelligent_heating_pilot/
```

**Note:** You only need to include `icon.png` and `icon@2x.png` since our logo is square. The icon will be used as a fallback for the logo automatically.

### Step 3: Commit and Push

```bash
git add custom_integrations/intelligent_heating_pilot/
git commit -m "Add Intelligent Heating Pilot custom integration icons"
git push origin main
```

### Step 4: Create Pull Request

1. Go to your fork on GitHub
2. Click "Contribute" → "Open pull request"
3. Fill in the PR description:
   ```
   Add icons for Intelligent Heating Pilot custom integration
   
   - Domain: intelligent_heating_pilot
   - Integration: https://github.com/RastaChaum/Intelligent-Heating-Pilot
   - Files: icon.png, icon@2x.png
   
   All images meet the requirements:
   - PNG format, optimized
   - 256x256 (icon.png) and 512x512 (icon@2x.png)
   - Transparent background, properly trimmed
   ```
4. Submit the pull request

### Step 5: Wait for Review

- The Home Assistant team will review your submission
- They may request changes if the images don't meet requirements
- Once approved and merged, the logo will be available at:
  - `https://brands.home-assistant.io/intelligent_heating_pilot/icon.png`
  - `https://brands.home-assistant.io/intelligent_heating_pilot/icon@2x.png`

### Step 6: Logo Appears in Home Assistant

After the PR is merged:
- Home Assistant will automatically fetch the logo from the brands repository
- It may take up to 7 days for the logo to appear due to browser caching
- Users can force-refresh (Ctrl+F5) to see it sooner
- The logo will appear on the Integrations page when installing or viewing the integration

## Image Requirements Reference

From the Home Assistant Brands repository:

### Icon Requirements
- ✅ Aspect ratio: 1:1 (square)
- ✅ Size: 256x256 pixels (normal), 512x512 pixels (hDPI)
- ✅ Format: PNG
- ✅ Optimized and compressed
- ✅ Transparent background preferred
- ✅ Properly trimmed (minimal empty space)
- ✅ Must not use Home Assistant branded images

### Logo Requirements (Optional)
- Landscape preferred
- Shortest side: 128-256px (normal), 256-512px (hDPI)
- Same format/quality requirements as icon

## Troubleshooting

### Logo Not Appearing After Merge

1. **Clear browser cache**: Press Ctrl+F5 (Windows/Linux) or Cmd+Shift+R (Mac)
2. **Wait for CDN**: Cloudflare caches images for 24 hours
3. **Full cache clear**: Images are cached for up to 7 days
4. **Verify URL**: Check if the image is accessible at `https://brands.home-assistant.io/intelligent_heating_pilot/icon.png`

### PR Rejected

Common reasons:
- Image too large (file size)
- Wrong dimensions
- Not properly trimmed
- Poor quality or pixelated
- Copyright issues

Fix the issues and update your PR with new commits.

## Alternative: Local Installation Note

Unfortunately, there is currently no way to display a logo on the Home Assistant Integrations page for locally-installed custom integrations without submitting to the brands repository. This is by design to maintain consistency and reduce package sizes.

The logo files in `custom_components/intelligent_heating_pilot/` are included for:
1. Future local support if Home Assistant adds this feature
2. Documentation purposes
3. Submission to the brands repository

## Resources

- [Home Assistant Brands Repository](https://github.com/home-assistant/brands)
- [Brands Repository README](https://github.com/home-assistant/brands/blob/master/README.md)
- [Developer Blog: Logos for Custom Integrations](https://developers.home-assistant.io/blog/2020/05/08/logos-custom-integrations/)
- [Image Optimization Tool](https://redketchup.io/image-resizer)

## Questions?

If you have questions about the logo submission process:
- Check the [Home Assistant Brands Issues](https://github.com/home-assistant/brands/issues)
- Ask in the [Home Assistant Community Forums](https://community.home-assistant.io/c/custom-integrations)
- Open an issue in the [IHP repository](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)
