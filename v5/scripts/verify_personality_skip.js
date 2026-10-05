async page => {
 await page.getByRole('combobox',{name:'我的 MBTI',exact:true}).selectOption('INFJ');
 await page.getByRole('combobox',{name:'现在希望怎样聊',exact:true}).selectOption('listen');
 await page.getByRole('button',{name:'暂不设定 MBTI',exact:true}).click();
 if(await page.locator('#userMbti').inputValue()!=='' || await page.locator('#supportMode').inputValue()!=='listen')throw Error('Skip changed explicit support need');
 await page.setViewportSize({width:1440,height:1000});
 await page.locator('.personality-setup').screenshot({path:'output/playwright/mbti-desktop.png'});
 await page.setViewportSize({width:390,height:844});
 if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Overflow');
 await page.locator('.personality-setup').screenshot({path:'output/playwright/mbti-mobile.png'});
 console.log('PASS: cancel MBTI preserves listening preference; final desktop/mobile layout checked.');
}
