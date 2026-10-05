import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
export default defineConfig({site:'https://njh7799.github.io',base:'/investment',output:'static',trailingSlash:'always',integrations:[react()]});
