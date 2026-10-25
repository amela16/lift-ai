import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',timeout:45000,use:{baseURL:process.env.TEST_BASE_URL||'http://127.0.0.1:5173',headless:true,screenshot:'only-on-failure'},reporter:'list',workers:1,
 projects:[
  {name:'chromium',testIgnore:/no-webgl/,use:{browserName:'chromium',launchOptions:{args:['--enable-unsafe-swiftshader']}}},
  // Browsers with WebGL turned off (driver blocklists, privacy settings) must still get a usable network view.
  {name:'firefox-no-webgl',testMatch:/no-webgl/,use:{browserName:'firefox',launchOptions:{firefoxUserPrefs:{'webgl.disabled':true}}}},
 ]});
