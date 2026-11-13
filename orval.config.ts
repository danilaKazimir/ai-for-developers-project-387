import { resolve } from 'node:path';
import { defineConfig } from 'orval';

const outputRoot = process.env.GENERATED_ROOT ?? process.cwd();

export default defineConfig({
  calendar: {
    input: resolve(outputRoot, 'api/generated/openapi.yaml'),
    output: {
      target: resolve(outputRoot, 'frontend/src/api/generated/calendar.ts'),
      schemas: resolve(outputRoot, 'frontend/src/api/generated/models'),
      client: 'react-query',
      httpClient: 'fetch',
      mode: 'split',
      clean: true,
      override: {
        mutator: {
          path: resolve(outputRoot, 'frontend/src/api/http.ts'),
          name: 'apiFetch',
        },
        fetch: {
          includeHttpResponseReturnType: false,
          forceSuccessResponse: true,
        },
      },
    },
  },
});

