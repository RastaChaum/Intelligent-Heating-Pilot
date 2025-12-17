"""Integration tests for Intelligent Heating Pilot component structure."""
import unittest
import json
import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../custom_components/intelligent_heating_pilot'))


class TestComponentStructure(unittest.TestCase):
    """Test the integration structure and configuration files."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_path = os.path.join(
            os.path.dirname(__file__),
            '../../custom_components/intelligent_heating_pilot'
        )

    def test_manifest_exists_and_valid(self):
        """Test that manifest.json exists and is valid."""
        manifest_path = os.path.join(self.base_path, 'manifest.json')
        self.assertTrue(os.path.exists(manifest_path))
        
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        # Check required fields
        self.assertIn('domain', manifest)
        self.assertIn('name', manifest)
        self.assertIn('version', manifest)
        self.assertIn('documentation', manifest)
        self.assertIn('issue_tracker', manifest)
        
        # Check domain matches expected
        self.assertEqual(manifest['domain'], 'intelligent_heating_pilot')

    def test_strings_json_exists_and_valid(self):
        """Test that strings.json exists and is valid."""
        strings_path = os.path.join(self.base_path, 'strings.json')
        self.assertTrue(os.path.exists(strings_path))
        
        with open(strings_path, 'r') as f:
            strings = json.load(f)
        
        # Check basic structure
        self.assertIn('config', strings)

    def test_services_yaml_exists(self):
        """Test that services.yaml exists."""
        services_path = os.path.join(self.base_path, 'services.yaml')
        self.assertTrue(os.path.exists(services_path))

    def test_translations_exist(self):
        """Test that translation files exist."""
        translations_path = os.path.join(self.base_path, 'translations')
        self.assertTrue(os.path.exists(translations_path))
        
        # Check for English and French translations
        en_path = os.path.join(translations_path, 'en.json')
        fr_path = os.path.join(translations_path, 'fr.json')
        
        self.assertTrue(os.path.exists(en_path))
        self.assertTrue(os.path.exists(fr_path))
        
        # Validate JSON structure
        with open(en_path, 'r') as f:
            en_trans = json.load(f)
        self.assertIn('config', en_trans)

    def test_hacs_json_exists(self):
        """Test that hacs.json exists in the root."""
        hacs_path = os.path.join(os.path.dirname(__file__), '../../hacs.json')
        self.assertTrue(os.path.exists(hacs_path))
        
        with open(hacs_path, 'r') as f:
            hacs_config = json.load(f)
        
        self.assertIn('name', hacs_config)
        self.assertIn('domains', hacs_config)
        self.assertIn('intelligent_heating_pilot', hacs_config['domains'])


if __name__ == '__main__':
    unittest.main()
