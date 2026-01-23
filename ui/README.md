# TFA Web UI

A modern web interface for the Test Failure Analyzer (TFA).

## Features

- **Dashboard**: Quick overview of system status and navigation
- **Quick Analysis**: Analyze test failures with AI-powered classification
- **Deep Investigation**: Thorough RCA using Thinker-Critic pattern
- **Statistics**: View trends and metrics (CLI redirect for now)

## Prerequisites

- Node.js 18+
- TFA API server running on port 8000

## Quick Start

### 1. Install Dependencies

```bash
cd ui
npm install
```

### 2. Start the TFA API Server

In a separate terminal, start the backend:

```bash
# From the project root
python main.py serve
```

### 3. Start the UI Development Server

```bash
npm run dev
```

The UI will be available at [http://localhost:3000](http://localhost:3000).

## Configuration

### API URL

By default, the UI proxies API requests to `http://localhost:8000`. To connect to a different API server, set the `VITE_API_URL` environment variable:

```bash
VITE_API_URL=http://tfa.internal:8000 npm run dev
```

Or create a `.env.local` file:

```env
VITE_API_URL=http://tfa.internal:8000
```

## Development

```bash
# Start development server with hot reload
npm run dev

# Type check
npm run build

# Lint
npm run lint
```

## Production Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

The built files will be in the `dist/` directory.

## Project Structure

```
ui/
├── src/
│   ├── api/           # API client
│   ├── components/    # Reusable UI components
│   ├── hooks/         # React hooks
│   ├── pages/         # Page components
│   ├── types/         # TypeScript types
│   ├── utils/         # Utility functions
│   ├── App.tsx        # Main app component
│   ├── main.tsx       # Entry point
│   └── index.css      # Global styles
├── public/            # Static assets
├── index.html         # HTML template
├── package.json       # Dependencies
├── tailwind.config.js # Tailwind CSS config
├── tsconfig.json      # TypeScript config
└── vite.config.ts     # Vite config
```

## CLI Integration

The UI complements the existing CLI. All CLI commands continue to work:

```bash
# CLI still works as before
python main.py analyze -l 9657 -c Model_server --push
python main.py investigate -l 9657 -c Model_server --push
python main.py stats --days 30
```

The UI provides a graphical alternative for common operations while the CLI remains available for automation, scripting, and advanced usage.
