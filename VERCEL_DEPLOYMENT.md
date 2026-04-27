# Vercel Deployment Guide

## 🚀 Deploy Knowledge Graph Builder to Vercel

This guide will help you deploy the Knowledge Graph Builder Swarm to Vercel's serverless platform.

## 📋 Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **GitHub Account**: For version control
3. **Gemini API Key**: For AI functionality

## 🛠️ Step-by-Step Deployment

### Step 1: Prepare Your Project

1. **Install Vercel CLI** (optional):
   ```bash
   npm i -g vercel
   ```

2. **Create GitHub Repository**:
   - Push your project to GitHub
   - Include all files in the `LEGAL CLAUSE` folder

### Step 2: Configure Environment Variables

In Vercel Dashboard → Project Settings → Environment Variables, add:

```bash
FLASK_SECRET_KEY=your-secure-random-string-here
GEMINI_API_KEY=your-gemini-api-key-here
```

### Step 3: Deploy to Vercel

#### Option A: Through Vercel Dashboard
1. Connect your GitHub repository
2. Vercel will auto-detect the Python project
3. Configure build settings:
   - **Build Command**: Leave empty (auto-detected)
   - **Output Directory**: Leave empty
   - **Install Command**: `pip install -r requirements-vercel.txt`

#### Option B: Using Vercel CLI
```bash
# Login to Vercel
vercel login

# Deploy from project directory
vercel --prod
```

### Step 4: Configure spaCy Model

The spaCy model needs to be downloaded. Add this to your `vercel.json`:

```json
{
  "functions": {
    "api/index.py": {
      "maxDuration": 30
    }
  }
}
```

And add this to your `api/index.py`:

```python
# Download spaCy model on first run
import subprocess
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except OSError:
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    import spacy
    nlp = spacy.load("en_core_web_sm")
```

## 🔧 Configuration Files

### `vercel.json`
```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ],
  "env": {
    "PYTHON_VERSION": "3.9"
  },
  "functions": {
    "api/index.py": {
      "maxDuration": 30
    }
  }
}
```

### `requirements-vercel.txt`
```
Flask>=2.3.0
Werkzeug>=2.3.0
spacy>=3.7.0
python-docx>=1.1.0
google-generativeai>=0.3.0
python-dotenv>=1.0.0
```

## 🌐 API Endpoints

Once deployed, your API will be available at:

```
https://your-app.vercel.app/api/process
https://your-app.vercel.app/api/qa
https://your-app.vercel.app/api/seed
https://your-app.vercel.app/api/status
```

## 🎯 Testing Your Deployment

### 1. Health Check
```bash
curl https://your-app.vercel.app/health
```

### 2. Status Check
```bash
curl https://your-app.vercel.app/api/status
```

### 3. Process Text
```bash
curl -X POST https://your-app.vercel.app/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo"}'

curl -X POST https://your-app.vercel.app/api/process \
  -H "Content-Type: application/json" \
  -d '{"text": "Elon Musk founded SpaceX in 2002."}'
```

### 4. Question Answering
```bash
curl -X POST https://your-app.vercel.app/api/qa \
  -H "Content-Type: application/json" \
  -d '{"question": "Who founded SpaceX?"}'
```

## 🚨 Important Notes

### Serverless Limitations
- **Execution Time**: Max 30 seconds per request
- **Memory**: Limited to 1GB per function
- **Cold Starts**: First request may be slower
- **Stateless**: Each request is independent

### Database Considerations
- **SQLite**: Works for demo, but limited in serverless
- **Production**: Consider PostgreSQL or MongoDB
- **Persistence**: In-memory storage resets between deployments

### File Uploads
- **Size Limit**: Vercel has file size restrictions
- **Alternative**: Use external storage (AWS S3, Cloudinary)

## 🔒 Security

### Environment Variables
- Never commit API keys to Git
- Use Vercel's environment variable management
- Rotate keys regularly

### Authentication
- Current demo uses simple authentication
- Production: Implement JWT or OAuth
- Rate limiting recommended

## 📈 Performance Optimization

### Cold Start Reduction
```python
# Add to api/index.py
from flask import g

@app.before_request
def before_request():
    g.nlp = get_nlp()  # Cache spaCy model
```

### Response Caching
```python
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

@app.route("/api/status")
@cache.cached(timeout=300)  # 5 minutes
def api_status():
    return jsonify({"status": "ok"})
```

## 🛠️ Troubleshooting

### Common Issues

#### 1. "Module Not Found" Error
- Ensure all dependencies are in `requirements-vercel.txt`
- Check Python version compatibility

#### 2. "Function Timeout" Error
- Increase `maxDuration` in `vercel.json`
- Optimize heavy operations

#### 3. "Memory Limit Exceeded"
- Reduce model sizes
- Implement streaming for large files

#### 4. "CORS Issues"
Add to `api/index.py`:
```python
from flask_cors import CORS

CORS(app)
```

### Debug Mode
Add to `vercel.json` for development:
```json
{
  "env": {
    "FLASK_ENV": "development",
    "FLASK_DEBUG": "1"
  }
}
```

## 🎉 Production Checklist

- [ ] Environment variables configured
- [ ] Custom domain set up
- [ ] SSL certificate enabled
- [ ] Monitoring and logging configured
- [ ] Rate limiting implemented
- [ ] Backup strategy for data
- [ ] Performance monitoring set up
- [ ] Error tracking configured

## 📚 Additional Resources

- [Vercel Python Documentation](https://vercel.com/docs/concepts/functions/serverless-functions)
- [Flask on Vercel Guide](https://vercel.com/guides/deploying-a-flask-app)
- [Serverless Best Practices](https://vercel.com/docs/concepts/functions/serverless-functions/practices)

## 🆘 Support

If you encounter issues:

1. Check Vercel deployment logs
2. Verify environment variables
3. Test locally with `vercel dev`
4. Check function timeout settings
5. Review memory usage patterns

Your Knowledge Graph Builder is now ready for serverless deployment on Vercel! 🚀
