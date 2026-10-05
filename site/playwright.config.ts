import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'*.spec.ts',timeout:60000,use:{baseURL:process.env.SITE_TEST_URL||'http://127.0.0.1:4322/investment/',headless:true},webServer:process.env.SITE_TEST_URL?undefined:{command:'pnpm preview --port 4322',url:'http://127.0.0.1:4322/investment/',reuseExistingServer:true},reporter:'list'});
