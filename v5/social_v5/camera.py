"""Loopback-only DirectShow bridge for cameras failing browser Media Foundation."""
import secrets
import threading
import time

import cv2
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response


class CameraBridge:
    def __init__(self):
        self.lock=threading.RLock();self.capture=None;self.lease=None;self.owner=None
        self.jpeg=None;self.last_poll=0;self.thread=None

    def start(self,owner):
        with self.lock:
            if self.capture is not None:
                raise HTTPException(409,'本机摄像头已被另一个对话页面使用，请先关闭那个页面的摄像头。')
            camera=cv2.VideoCapture(0,cv2.CAP_DSHOW)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH,640);camera.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            ok,frame=camera.read()
            if not ok:
                camera.release()
                raise HTTPException(503,'本机兼容采集也无法读取摄像头。请检查摄像头遮挡开关及占用它的应用后重试。')
            ok,jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,82])
            if not ok:
                camera.release();raise HTTPException(503,'无法编码摄像头画面，请重试。')
            self.capture=camera;self.jpeg=jpeg.tobytes();self.owner=owner
            self.lease=secrets.token_urlsafe(32);self.last_poll=time.monotonic()
            lease=self.lease
            self.thread=threading.Thread(target=self._read,args=(camera,lease),daemon=True,name='camera-directshow')
            self.thread.start()
            return {'lease':lease,'mode':'local_directshow','width':frame.shape[1],'height':frame.shape[0],'raw_images_stored':False}

    def _read(self,camera,lease):
        try:
            while True:
                with self.lock:
                    if self.lease!=lease or time.monotonic()-self.last_poll>6:break
                ok,frame=camera.read()
                if not ok:break
                ok,jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,82])
                with self.lock:
                    if self.lease!=lease:break
                    if ok:self.jpeg=jpeg.tobytes()
                time.sleep(.08)
        finally:
            camera.release()
            with self.lock:
                if self.lease==lease:
                    self.capture=None;self.lease=None;self.owner=None;self.jpeg=None

    def frame(self,owner,lease):
        with self.lock:
            if not lease or lease!=self.lease or owner!=self.owner:
                raise HTTPException(410,'摄像头连接已结束，请重新开启。')
            self.last_poll=time.monotonic()
            return self.jpeg

    def stop(self,owner=None,lease=None):
        with self.lock:
            if owner is not None and (owner!=self.owner or lease!=self.lease):return
            thread=self.thread;self.lease=None
        if thread:thread.join(timeout=2)
        with self.lock:
            self.capture=None;self.owner=None;self.jpeg=None


bridge=CameraBridge()


def router(guard):
    def local(request:Request):
        if not request.client or request.client.host not in {'127.0.0.1','::1','testclient'}:
            raise HTTPException(403,'本机兼容摄像头只允许本机访问。')

    def owner(request):
        return request.state.guest_id+':'+request.headers.get('x-member-session','')

    api=APIRouter(prefix='/v1/camera',dependencies=[Depends(guard),Depends(local)])

    @api.post('/start')
    def start(request:Request):return bridge.start(owner(request))

    @api.get('/frame')
    def frame(request:Request,x_camera_lease:str=Header(default='')):
        return Response(bridge.frame(owner(request),x_camera_lease),media_type='image/jpeg',headers={'Cache-Control':'no-store'})

    @api.post('/stop')
    def stop(request:Request,x_camera_lease:str=Header(default='')):
        bridge.stop(owner(request),x_camera_lease);return {'stopped':True}

    return api
