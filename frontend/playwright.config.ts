import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',timeout:45000,use:{baseURL:process.env.TEST_BASE_URL||'http://127.0.0.1:5173',headless:true,launchOptions:{args:['--enable-unsafe-swiftshader']},screenshot:'only-on-failure'},reporter:'list',workers:1});
