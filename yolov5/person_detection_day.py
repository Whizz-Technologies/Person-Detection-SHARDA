import cv2
import numpy as np
import os
from elements.yolo import OBJ_DETECTION
from email_sender import send_email
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
import datetime
import time
from pyembedded.raspberry_pi_tools.raspberrypi import PI
pi = PI()
from check_internet_connectivity import is_connected
from sent_status_every_12_hours import check_if_12_hours
from logger import log_data
import func_timeout


def getserial():
  # Extract serial from cpuinfo file
  cpuserial = "0000000000000000"
  try:
    f = open('/proc/cpuinfo','r')
    for line in f:
      if line[0:6]=='Serial':
        cpuserial = line[10:26]
    f.close()
  except:
    cpuserial = "ERROR000000000"
 
  return cpuserial


def register(serial):
    myserial =  serial
    #myserial = "45455656128"
    url = "http://65.2.177.76/api/assign-hardware-device"

    #payload="{\n   \n \"hardwar_id\" :\"devicde_serial_no\"\n      \n        \n}"
    payload = "{ \n \"hardware_number\" : \"" + myserial + "\" \n}"
    print(payload)
    headers = {
    'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    
    response = response.json()
    print(response)
    device_id = str(response['my_devices_detail'][0]['device_number'])
    print('device id',device_id)
    with open('./device_id.txt', 'w') as f:
        f.write(device_id)
        f.close()
    return "Device id written to file"


def request_status(device_id):
  url = "http://as99.zvastica.solutions/appapi/checkdevicestatusbyhw"

  #payload = "{\n    \"device_id\":\"2\"\n }"
  payload = "{ \n \n \"device_id\" : " + device_id + " \n \n \n}"
  headers = {
    'Content-Type': 'application/json'
  }

  response = requests.request("POST", url, headers=headers, data = payload)

  str = response.text.split(',')

  status = str[1].split(':')

  return status[1]

def write_log(detection):
    
    try:
    
        file_path = '/home/pi/Person-Detection-SHARDA/yolov5/log.txt'
        #get file size
        fileSize = os.path.getsize(file_path)
        filesize_GB =  (fileSize/(1024*1024*1024))
        if filesize_GB > 1:
            #remove label.txt
            os.remove(file_path)
        with open('/home/pi/Person-Detection-SHARDA/yolov5/log.txt', 'a') as f:
            #write the date and time
            f.write(time.strftime("%d/%m/%Y %H:%M:%S"))
            f.write('\n')
            f.write("Number of Detection: " +  str(detection))
            f.write('\n')
            f.write('Cpu Usage is' +  str(pi.get_cpu_usage()))
            f.write('\n')
            f.write('Memory Usage is ' + str( pi.get_ram_info()))
            f.write('\n')
            f.write('CPU temperature is ' +  str(pi.get_cpu_temp()))
            f.write('\n')
            
    except:
        pass


def send_video_file(device_id,file_path):

    url = "http://65.2.177.76/api/add-video"
    now = datetime.datetime.now(datetime.timezone.utc)
    date_time_str = now.isoformat()
    data = {
        'device_number' : str(device_id),
        'video_file': ('vv.mp4', open(file_path, 'rb'), 'text/plain')
    }

    multipart_data = MultipartEncoder(data)

    try:

        server = requests.post(url, data=multipart_data, headers={'Content-Type': multipart_data.content_type})
        output = server.text
        print('The response from the server is: \n', output)
        
        return True

    except:
        return False

    

def sent_video(device_id):

    max_wait = 60

    for file in os.listdir('/home/pi/Person-Detection-SHARDA/yolov5//output'):
        

        file_path = os.path.join('/home/pi/Person-Detection-SHARDA/yolov5//output', file)


        try:
            #response = request("POST", url, headers=headers, data = payload, files = files)
            y = func_timeout.func_timeout(max_wait, send_video_file, args = [device_id,file_path])
            if (y == True):
                #print("Video sent")
                os.remove(file_path)
            else:
                #print("Video not sent")
                return False
        except func_timeout.FunctionTimedOut:
            #print("Timeout")
            return False

    #check if output dir is empty
    if not os.listdir('/home/pi/Person-Detection-SHARDA/yolov5//output'):
        #print("No files to send")
        return True
            

    #remove contents of output folder
    for file in os.listdir('/home/pi/Person-Detection-SHARDA/yolov5//output'):
        file_path = os.path.join('/home/pi/Person-Detection-SHARDA/yolov5//output', file)
        os.remove(file_path)
    

    return True

def predict():

    prev_time = 0
    new_time = time.time()
    record_time = time.time()

    video_sent_status = False
    number_of_person_detected = 0
    previous_number_of_person_detected = {'Number' : 0 , 'Time' : time.time()}
    meta_of_number_of_person_detected = {'Number' : 0 , 'frame_number' : 0 , 'number_of_frames_not_detected' : 0}
    frames_counter = 0
    frames = []
    not_detected_frames_thresh = 10
    number_of_frames_not_detected = 0



    #if is_cache does not exist, create it
    if not os.path.exists('/home/pi/Person-Detection-SHARDA/yolov5/is_cache.txt'):
        with open('/home/pi/Person-Detection-SHARDA/yolov5/is_cache.txt', 'w') as f:
            f.write('')
            f.close()
    
    #read is_cached from file
    with open('/home/pi/Person-Detection-SHARDA/yolov5//is_cached.txt', 'r') as f:
        is_cached = f.read()
        ##print(type(bool(is_cached)))
        if("True" in is_cached):
            is_cached = True

        else:
            is_cached = False
        f.close()


    if is_cached == '':
        is_cached = False
        #write is_cached to file
        with open('/home/pi/Person-Detection-SHARDA/yolov5//is_cached.txt', 'w') as f:
            f.write(str(is_cached))
            f.close()

    
    Object_classes = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light',
                    'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
                    'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
                    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
                    'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
                    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
                    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
                    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
                    'hair drier', 'toothbrush' ]

    #Object_colors = list(np.random.rand(80,3)*255)
    Object_detector = OBJ_DETECTION('/home/pi/Person-Detection-SHARDA/yolov5/yolov5n-int8.tflite', Object_classes)
    
    cap = cv2.VideoCapture('./output.avi')
    serial = getserial()
    REMOTE_SERVER = "www.google.com"
    if is_connected(REMOTE_SERVER):
        registration_status = register(serial)
        
    else:
        registration_status = "Device id written to file"
        
    if(registration_status == "Device id written to file"):
        #read the device id from the text file
        with open('/home/pi/Person-Detection-SHARDA/yolov5/device_id.txt', 'r') as f:
            device_id = f.read()
            f.close()
            
    device_id_temp = device_id[1:-1]
    with open('/home/pi/Desktop/Client/input.txt','w') as f:
        f.write(device_id_temp)
        f.write('\n')
        f.write(serial)
        
    with open('/home/pi/Desktop/Client/test','r') as f:
        lines = f.readlines()
        ##print(lines)
    f.close()
    if(lines[0] == "True"):
        status_of_device = 'true'

    else:
        status_of_device = 'false'
    

    while cap.isOpened():

        with open('/home/pi/Desktop/Client/test','r') as f:
            lines = f.readlines()
            ##print(lines)
        f.close()
        ##print("Type of lines[0]",type(lines[0]))
        if(lines[0] == "True"):
            status_of_device = 'true'

        elif(lines[0] == "False"):
            status_of_device = 'false'
        
        
        print("Status of Device",status_of_device)
        REMOTE_SERVER = "www.google.com"
        if is_connected(REMOTE_SERVER):
            #print("connected")
            cache = False
            with open('/home/pi/Person-Detection-SHARDA/yolov5//is_cache.txt','w') as f:
                f.write(str(cache))
                f.close
            try:

                log_data(device_id)
                check_if_12_hours(device_id)

            except:
                
                print("Error as ", e , "In log Data Module or Check if 12 hours")
                pass
        
            if( is_cached == True):
                #print("Cached")
                #print(device_id)
                video_sent_status = sent_video(device_id)
                if(video_sent_status == True):
                    is_cached = False
                #write is_cached to file
                with open('/home/pi/Person-Detection-SHARDA/yolov5//is_cached.txt', 'w') as f:
                    f.write(str(is_cached))
                    f.close()


        else:
            #print("not connected")
            cache = True
            with open('/home/pi/Person-Detection-SHARDA/yolov5//is_cache.txt', 'w') as f:
                f.write(str(cache))
                f.close()
        
        ret, frame = cap.read()
        new_time = time.time()
    
        if ret and status_of_device == 'true':
            # detection process
            objs = Object_detector.detect(frame)
            dets = []
            # plotting
            
            number_of_person_detected = 0

            for obj in objs:
                # #print(obj)
                label = obj['label']
                score = obj['score']
                if((label == 'person') and score > 0.5 ):
                    number_of_frames_not_detected = 0
                    number_of_person_detected +=1
                    ##print(label)
                    
                    [(xmin,ymin),(xmax,ymax)] = obj['bbox']
                    ##print(xmin,ymin,xmax,ymax)
                    (x, y) = (xmin, ymin)
                    (w, h) = ((xmax-xmin),(ymax-ymin))
                    #color = Object_colors[Object_classes.index(label)]
                    frame = cv2.rectangle(frame, (xmin,ymin), (xmax,ymax), (255,0,0), 2) 
                    frame = cv2.putText(frame, f'{label} ({str(score)})', (xmin,ymin), cv2.FONT_HERSHEY_SIMPLEX , 0.75, (0,255,255), 1, cv2.LINE_AA)


                



            
            if(number_of_person_detected > meta_of_number_of_person_detected['Number'] or number_of_person_detected < meta_of_number_of_person_detected['Number']):
                if(number_of_person_detected == 0):
                    meta_of_number_of_person_detected['number_of_frames_not_detected'] +=1

                    if(meta_of_number_of_person_detected['number_of_frames_not_detected'] > not_detected_frames_thresh):
                        meta_of_number_of_person_detected['Number'] = number_of_person_detected
                
                        meta_of_number_of_person_detected['frame_number'] = 1
                if(number_of_person_detected > 0):
                    meta_of_number_of_person_detected['number_of_frames_not_detected'] = 0
                    meta_of_number_of_person_detected['Number'] = number_of_person_detected
                    meta_of_number_of_person_detected['frame_number'] +=1

            if(number_of_person_detected == meta_of_number_of_person_detected['Number']):
                meta_of_number_of_person_detected['frame_number'] += 1
            
            #print("Frames Counter", frames_counter)
            #print("Number of person detected:", meta_of_number_of_person_detected, "Previous number of person detected:", previous_number_of_person_detected)
            if((meta_of_number_of_person_detected['Number'] > previous_number_of_person_detected['Number']) and meta_of_number_of_person_detected['frame_number'] > 10):
                #print("New Person Detected")
                previous_number_of_person_detected['Number'] = meta_of_number_of_person_detected['Number']
                #previous_number_of_person_detected['Time'] = number_of_person_detected['Time']
                if(video_sent_status == True):
                    video_sent_status = False
                    frames_counter = 0


            elif((meta_of_number_of_person_detected['Number'] < previous_number_of_person_detected['Number']) and meta_of_number_of_person_detected['frame_number'] > 10):
                #print("Person Detected Reduced")
                previous_number_of_person_detected['Number'] = meta_of_number_of_person_detected['Number']
                #previous_number_of_person_detected['Time'] = number_of_person_detected['Time']
                if(video_sent_status == True):
                    video_sent_status = False
                    frames_counter = 0


            if(video_sent_status == False and previous_number_of_person_detected['Number'] > 0):
                if(frames_counter == 30):
                    #play sound
                    #play_sound(40)
                    pass
                if(frames_counter < 31):
                    frames_counter = frames_counter + 1
                    frames.append(frame)
                elif(frames_counter == 31):
                    frames_counter = frames_counter + 1
                    REMOTE_SERVER = "www.google.com"
                    if is_connected(REMOTE_SERVER):
                        #print("connected")
                        cache = False
                        with open('/home/pi/Person-Detection-SHARDA/yolov5//is_cache.txt', 'w') as f:
                            f.write(str(cache))
                            f.close()

                    else:
                        #print("not connected")
                        cache = True
                        with open('/home/pi/Person-Detection-SHARDA/yolov5//is_cache.txt', 'w') as f:
                            f.write(str(cache))
                            f.close()
                    if(cache == False):
                        #write a list of frames in a video
                        current_file_number = 0
                        output_file_save_name = '/home/pi/Person-Detection-SHARDA/yolov5/output/output_' + str(current_file_number) + '.mp4'
                        out = cv2.VideoWriter(output_file_save_name,cv2.VideoWriter_fourcc(*'avc1'), 10, (frame.shape[1],frame.shape[0]))
                        for i in range(len(frames)):
                            out.write(frames[i])
                        out.release()
                        #print(device_id)
                        video_sent_status = sent_video(device_id)
                        #if video_sent_status == True:
                            #print("Video sent")
                        frames = []

                    if(cache == True):
                        current_file_number = 0
                        #find the folders in the cache folder
                        for file in os.listdir('/home/pi/Person-Detection-SHARDA/yolov5/output'):
                            if file.endswith(".mp4"):
                                file_number = file.split("_")[1]
                                file_number = file_number.split(".")[0]

                                if(int(file_number) > current_file_number):
                                    current_file_number = int(file_number)

                        output_file_save_name = "/home/pi/Person-Detection-SHARDA/yolov5/output/output_" + str(current_file_number + 1) + ".mp4"
                        out = cv2.VideoWriter(output_file_save_name,cv2.VideoWriter_fourcc(*'avc1'), 10, (frame.shape[1],frame.shape[0]))
                        for i in range(len(frames)):
                            out.write(frames[i])
                        out.release()
                        #print(device_id)
                        is_cached = True
                        #write is_cached to a file
                        with open('/home/pi/Person-Detection-SHARDA/yolov5/is_cached.txt', 'w') as f:
                            f.write(str(is_cached))
                        frames = []


            #print("Number of Frames not detected" , number_of_frames_not_detected)
            if(number_of_frames_not_detected < not_detected_frames_thresh and number_of_person_detected == 0):
                    number_of_frames_not_detected = number_of_frames_not_detected + 1
            elif(number_of_frames_not_detected >= not_detected_frames_thresh and number_of_person_detected == 0):
                    video_sent_status = False
                    if(frames_counter >= 10):
                        frames_counter = frames_counter + 1
                        REMOTE_SERVER = "www.google.com"
                        if is_connected(REMOTE_SERVER):
                            #print("connected")
                            cache = False
                            with open('/home/pi/Person-Detection-SHARDA/yolov5/is_cache.txt', 'w') as f:
                                f.write(str(cache))
                                f.close()

                        else:
                            #print("not connected")
                            cache = True
                            with open('/home/pi/Person-Detection-SHARDA/yolov5/is_cache.txt', 'w') as f:
                                f.write(str(cache))
                                f.close()
                        if(cache == False):
                            #write a list of frames in a video
                            current_file_number = 0
                            output_file_save_name = '/home/pi/Person-Detection-SHARDA/yolov5/output/output_' + str(current_file_number) + '.mp4'
                            out = cv2.VideoWriter(output_file_save_name,cv2.VideoWriter_fourcc(*'avc1'), 10, (frame.shape[1],frame.shape[0]))
                            for i in range(len(frames)):
                                out.write(frames[i])
                            out.release()
                            #print(device_id)
                            video_sent_status = sent_video(device_id)
                            #if video_sent_status == True:
                                #print("Video sent")
                            frames = []

                        if(cache == True):
                            current_file_number = 0
                            #find the folders in the cache folder
                            for file in os.listdir('/home/pi/Person-Detection-SHARDA/yolov5/output'):
                                if file.endswith(".mp4"):
                                    file_number = file.split("_")[1]
                                    file_number = file_number.split(".")[0]

                                    if(int(file_number) > current_file_number):
                                        current_file_number = int(file_number)

                            output_file_save_name = "/home/pi/Person-Detection-SHARDA/yolov5/output/output_" + str(current_file_number + 1) + ".mp4"
                            out = cv2.VideoWriter(output_file_save_name,cv2.VideoWriter_fourcc(*'avc1'), 10, (frame.shape[1],frame.shape[0]))
                            for i in range(len(frames)):
                                out.write(frames[i])
                            out.release()
                            #print(device_id)
                            is_cached = True
                            #write is_cached to a file
                            with open('/home/pi/Person-Detection-SHARDA/yolov5/is_cached.txt', 'w') as f:
                                f.write(str(is_cached))
                            
                    frames_counter = 0
                    frames = []
                    number_of_person_detected = 0
                    previous_number_of_person_detected['Number'] = 0


        if(time.time() - record_time >= 1):
            record_time = time.time()
            write_log(number_of_person_detected)
        
        frame = cv2.resize(frame,(640,480))
        cv2.imshow("CSI Camera", frame)
        keyCode = cv2.waitKey(30)
        if keyCode == ord('q'):
                break      
    #cap.release()
    #cv2.destroyAllWindows()



if __name__ == "__main__":
    predict()
