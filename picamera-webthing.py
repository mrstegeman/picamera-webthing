# -*- coding: utf-8 -*-

#!/usr/bin/env python3

from asyncio import sleep, CancelledError, get_event_loop
from webthing import (Action, Event, Property, Value, SingleThing, Thing, WebThingServer)
import picamera
import io
import threading
import time
import syslog
import base64

#import os
#import uuid
#import sys
#import platform
#import datetime

class MyPiCamera:
    """A wrapper class for raspberry pi camera"""

    def __init__(self):

        self.device_name = "picam"
        # pi camera settings
        self.use_video_port = False
        #self.framerate = 1.0
        self.iso = 0
        self.rotation = 0
        self.shutter_speed = 0
        self.sensor_mode = 3
        self.exposure_mode = "auto"
        self.resolution = (1024, 768)
        self.camera = picamera.PiCamera()
        self.camera_setup()

    def cleanup(self):
        self.camera.stop_preview()
        self.camera.close()

    def camera_setup(self):

        self.camera_lock = threading.Lock()

        with self.camera_lock:
            self.camera.resolution = self.resolution
            self.camera.rotation = self.rotation
            self.camera.iso = self.iso
            """
                We set the framerate to 30.0 at startup so the firmware has at
                least 90 frames (30 * 3 seconds) to use for calibrating the sensor,
                which is critical in low light. May need to do this periodically
                as well; if the framerate is set very low the camera will take
                several minutes or longer to react to lighting changes
            """
            #self.camera.framerate = 30.0
            #self.camera.shutter_speed = self.shutter_speed
            #self.camera.sensor_mode = self.sensor_mode
            #self.camera.exposure_mode = self.exposure_mode
            # may not be necessary, night mode seems to do it automatically
            #self.camera.framerate_range = (0.1, self.framerate)
            self.camera.start_preview()

        syslog.syslog('Waiting for camera module warmup...')
        """
            Give the camera firmware a chance to calibrate the sensor, critical
            for low light
        """
        time.sleep(3)

        #with self.camera_lock:
        """
                now set the framerate back to the configured value
        """
            #self.camera.framerate = self.framerate

    def get_still_image(self, path):
        """
            This uses base64 for the image data so the gateway doesn't have to do
            anything but pass it to the `img` tag using the well known inline syntax
        """
        #_image_stream = io.BytesIO()
        syslog.syslog("Capturing image ...")#, self.use_video_port)

        with self.camera_lock:
            # image quality higher than 10 tends to make large images with no
            # meaningful quality improvement.
            #cap_start = time.time()
            #self.camera.capture(path, format = 'jpeg', quality = 10, thumbnail = None, use_video_port = self.use_video_port)
            self.camera.capture(path, format = 'jpeg', use_video_port = self.use_video_port)
            
            #cap_end = time.time()
            #logger.debug("Capture took %f seconds", (cap_end - cap_start))

        #_image_stream.seek(0)
        #image = base64.b64encode(_image_stream.getvalue())
        #_image_stream.close()
        #return image

    def get_resolution(self):
        """
            This formats the resolution as WxH, which the picamera API will actually
            accept when setting the value in set_resolution(), so it works out
            quite well as we can pass resolution back and forth all the way up
            to the Gateway interface as-is without any further parsing or
            formatting
        """
        with self.camera_lock:
            _width, _height = self.camera.resolution
        resolution = "{}x{}".format(_width, _height)
        return resolution

    def set_resolution(self, resolution):
        with self.camera_lock:
            try:
                self.camera.resolution = resolution
                self.resolution = resolution
                return True
            except Exception as e:
                syslog.syslog("Failed to set resolution")
                return False

    def get_framerate(self):
        with self.camera_lock:
            _fr = float(self.camera.framerate)
        framerate = "{}".format(_fr)
        return framerate

    def set_framerate(self, framerate):
        with self.camera_lock:
            try:
                self.camera.framerate = framerate
                self.framerate = framerate
                return True
            except Exception as e:
                syslog.syslog("Failed to set framerate")
                return False

    def get_exposure_mode(self):
        with self.camera_lock:
            _ex = self.camera.exposure_mode
        return _ex

    def set_exposure_mode(self, exposure_mode):
        with self.camera_lock:
            try:
                self.camera.exposure_mode = exposure_mode
                self.exposure_mode = exposure_mode
                return True
            except Exception as e:
                syslog.syslog("Failed to set exposure mode")
                return False

class PiCameraThing(Thing):
    """A web connected Pi Camera"""
    def __init__(self):
        Thing.__init__(self,
                       'urn:dev:ops:my-picam-thing-1234',
                       'My PiCamera Thing',
                       ['Camera'],#[VideoCamera],
                       'A web connected Pi Camera')
        self.picam = MyPiCamera()
        
        self.still_img = Value(None)
        self.add_property(
            Property(self, 'snapshot', self.still_img,
                    metadata = {
                                '@type': 'ImageProperty',
                                'title': 'Snapshot',
                                'type': 'null',
                                'readOnly': True,
                                'links': [
                                         {
                                            'rel': 'alternate',
                                            'href': '/home/pi/picamera-webthing/screenshots/snapshot.jpg',
                                            'mediaType': 'image/jpeg'
                                         }
                                         ]
                                }))
        syslog.syslog('Starting the camera update loop')
        self.picam_task = get_event_loop().create_task(self.update_PiCam())
    
    async def update_PiCam(self):
        while True:
            try:
                self.picam.get_still_image('/home/pi/picamera-webthing/screenshots/snapshot.jpg')
                #if self.still_img is not None and image is not None:
                #    self.ioloop.add_callback(self.base64_still_image_value.notify_of_external_update,
                #                             image.decode('utf-8'))
            except Exception as e:
                #print(e)
                syslog.syslog('Exception occured while updating image property')
            wait_interval = 10.0# / float(self.picam.framerate)
            #syslog.syslog("Camera sleeping for %.2f (fps: %.2f)", wait_interval, float(self.framerate))

            await sleep(wait_interval)

    def cancel_tasks(self):
        self.picam_task.cancel()
        get_event_loop().run_until_complete(self.picam_task)

if __name__ == '__main__':
    picamera_web_thing = PiCameraThing()
    server = WebThingServer(SingleThing(picamera_web_thing), port=8900)
    try:
        syslog.syslog('Starting the Webthing server on: ' + str(server.hosts))
        server.start()
    except KeyboardInterrupt:
        picamera_web_thing.cancel_tasks()
        picamera_web_thing.picam.camera.stop()
    finally:
        picamera_web_thing.picam.cleanup()
