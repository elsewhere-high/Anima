async (page) => {
  await page.getByText('数据管理',{exact:true}).click();
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'删除我的成员资料',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('currentMember').textContent==='访客');
  return {temporary_member_deleted:true};
}
