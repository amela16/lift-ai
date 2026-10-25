import {test,expect} from '@playwright/test';
test('without WebGL the network falls back to a 2D view in both modes',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('/');
 await expect(page.locator('tbody tr').first()).toBeVisible({timeout:30000});
 const fallback=page.locator('.network-2d');
 await expect(fallback).toBeVisible();
 await expect(page.getByText('3D is unavailable')).toHaveCount(0);
 expect(await fallback.locator('line').count()).toBeGreaterThan(400);
 expect(await fallback.locator('circle').count()).toBeGreaterThan(300);
 await page.getByRole('button',{name:'Berlin map',exact:true}).click();
 await expect(fallback).toBeVisible();
 await fallback.locator('circle.no-lift').first().click();
 await expect(page.getByRole('dialog')).toBeVisible();
 expect(errors).toEqual([]);
});
