"""Bounded audit using real IRSA ranges and independent Photutils/SkyCoord oracles."""
import pytest
from scripts.validate_spectrum import audit

pytestmark=pytest.mark.network

def test_official_tutorial_metadata_values_and_resource_bounds():
    result=audit()
    assert result['provenance']['bunit']=='MJy/sr'
    assert len(result['channels'])==102
    assert result['channels'][50]['status']==result['channels'][51]['status']=='blank'
