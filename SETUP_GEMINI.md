# Gemini API Integration Setup Guide

This guide explains how to set up the Gemini API integration for the Knowledge Graph Builder.

## Prerequisites

1. **Google Account**: You need a Google account to access the Gemini API
2. **API Access**: Request access to Google AI Studio

## Step 1: Get Your Gemini API Key

1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the generated API key

## Step 2: Configure Environment

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file and add your Gemini API key:
   ```
   GEMINI_API_KEY=your-actual-api-key-here
   ```

3. Also set a secure Flask secret key:
   ```
   FLASK_SECRET_KEY=your-secure-random-string-here
   ```

## Step 3: Install Dependencies

Install the required packages including the Gemini API client:

```bash
pip install -r requirements.txt
```

## Step 4: Verify Installation

Run the application and check the console output. You should see:

- If successful: "Gemini API initialized successfully."
- If missing API key: "Warning: GEMINI_API_KEY environment variable not set."

## Step 5: Test the Integration

1. Start the application:
   ```bash
   python app.py
   ```

2. Process some text and check if you see enhancement messages like:
   "[Gemini enhanced: +X entities, +Y relations]"

3. Test the enhanced question answering:
   - Ask questions like "What companies are mentioned?" or "Who founded SpaceX?"
   - The system will use Gemini API first for intelligent answers
   - If Gemini is unavailable, it falls back to rule-based answers

## How Gemini Enhances Knowledge Graph

The Gemini API integration provides:

1. **Better Entity Recognition**: Identifies entities that spaCy might miss
2. **Improved Relation Extraction**: Finds more meaningful relationships
3. **Enhanced Accuracy**: Combines rule-based and AI-powered extraction
4. **Intelligent Question Answering**: Uses Gemini for natural language QA with fallback to rules
5. **Context-Aware Answers**: Leverages original text and knowledge graph for better responses
6. **Fallback Support**: Works normally even if Gemini API is unavailable

## Features

- **Automatic Fallback**: If Gemini API is unavailable, the system uses spaCy only
- **Error Handling**: API errors don't crash the application
- **Performance Optimized**: Gemini API calls are made asynchronously
- **Cost Conscious**: Only calls Gemini when configured, no unnecessary API usage

## Troubleshooting

### Issue: "Gemini API not available"
- **Solution**: Check that GEMINI_API_KEY is set in your environment
- **Command**: `echo $GEMINI_API_KEY` (Linux/Mac) or `echo %GEMINI_API_KEY%` (Windows)

### Issue: API quota exceeded
- **Solution**: Check your Google AI Studio quota and usage limits
- **Alternative**: The app will continue working with spaCy only

### Issue: Invalid API key
- **Solution**: Verify your API key from Google AI Studio is correct
- **Check**: Ensure no extra spaces or characters in the API key

## API Usage Notes

- The integration uses the `gemini-pro` model for text processing
- Each text processing request makes one API call to Gemini
- The app gracefully handles API failures and falls back to spaCy
- Enhancement information is logged in the sentences array for debugging
