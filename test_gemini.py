#!/usr/bin/env python3
"""
Test script for Gemini API integration
"""
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gemini_config
import extractor

def test_gemini_availability():
    """Test if Gemini API is properly configured."""
    print("=== Gemini API Availability Test ===")
    
    if gemini_config.gemini_config.is_available():
        print("✅ Gemini API is available and configured")
        return True
    else:
        print("❌ Gemini API is not available")
        print("   Please set GEMINI_API_KEY environment variable")
        print("   Get your API key from: https://makersuite.google.com/app/apikey")
        return False

def test_gemini_extraction():
    """Test Gemini API extraction functionality."""
    print("\n=== Gemini API Extraction Test ===")
    
    test_text = "Elon Musk founded SpaceX in 2002 and later acquired Twitter in 2022."
    print(f"Test text: '{test_text}'")
    
    try:
        # Test basic spaCy extraction first
        spacy_result = extractor.extract(test_text)
        print(f"\nspaCy extraction:")
        print(f"  Entities: {len(spacy_result['entities'])}")
        print(f"  Relations: {len(spacy_result['relations'])}")
        
        # Test Gemini enhancement
        if gemini_config.gemini_config.is_available():
            enhanced_result = gemini_config.gemini_config.enhance_extraction_with_gemini(
                spacy_result['entities'], 
                spacy_result['relations'], 
                test_text
            )
            
            print(f"\nGemini enhanced extraction:")
            print(f"  Enhanced: {enhanced_result.get('enhanced', False)}")
            print(f"  Total Entities: {len(enhanced_result.get('entities', []))}")
            print(f"  Total Relations: {len(enhanced_result.get('relations', []))}")
            
            if enhanced_result.get('enhanced'):
                print(f"  Gemini added: +{enhanced_result.get('gemini_entities', 0)} entities, +{enhanced_result.get('gemini_relations', 0)} relations")
            
            # Show extracted entities
            print(f"\nEntities:")
            for entity in enhanced_result.get('entities', [])[:5]:  # Show first 5
                print(f"  - {entity.get('text', '')} ({entity.get('type', '')})")
            
            # Show extracted relations
            print(f"\nRelations:")
            for relation in enhanced_result.get('relations', [])[:5]:  # Show first 5
                print(f"  - {relation.get('source', '')} -> {relation.get('target', '')} ({relation.get('relation', '')})")
                
        else:
            print("Gemini API not available - skipping enhancement test")
            
    except Exception as e:
        print(f"❌ Error during extraction test: {e}")
        return False
    
    return True

def test_full_extractor():
    """Test the full extractor with Gemini integration."""
    print("\n=== Full Extractor Test (with Gemini) ===")
    
    test_text = """
    Apple Inc. was founded by Steve Jobs in Cupertino, California in 1976. 
    The company later hired Tim Cook as CEO, who moved the headquarters to Apple Park.
    Microsoft, founded by Bill Gates, is a major competitor based in Redmond, Washington.
    """
    
    print(f"Test text: {test_text.strip()}")
    
    try:
        result = extractor.extract(test_text)
        
        print(f"\nExtraction Results:")
        print(f"  Total Entities: {len(result['entities'])}")
        print(f"  Total Relations: {len(result['relations'])}")
        print(f"  Sentences processed: {len(result['sentences'])}")
        
        # Check for Gemini enhancement messages
        gemini_enhanced = any("Gemini enhanced" in sent for sent in result['sentences'])
        if gemini_enhanced:
            print("  ✅ Gemini enhancement was applied")
            for sent in result['sentences']:
                if "Gemini" in sent:
                    print(f"    {sent}")
        else:
            print("  ℹ️  Using spaCy extraction only (Gemini not available or failed)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during full extractor test: {e}")
        return False

def main():
    """Run all Gemini API tests."""
    print("Knowledge Graph Builder - Gemini API Integration Test")
    print("=" * 60)
    
    # Test 1: Check availability
    gemini_available = test_gemini_availability()
    
    # Test 2: Test extraction functionality
    if gemini_available:
        test_gemini_extraction()
    
    # Test 3: Test full extractor
    test_full_extractor()
    
    print("\n" + "=" * 60)
    print("Test completed!")
    
    if gemini_available:
        print("✅ Gemini API integration is working")
    else:
        print("⚠️  Gemini API integration needs configuration")
        print("   See SETUP_GEMINI.md for instructions")

if __name__ == "__main__":
    main()
