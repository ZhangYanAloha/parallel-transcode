#!/usr/bin/env python
#coding:utf-8
# Author: Beining  --<ACICFG>
# Purpose: Parallel-Transcode a file.
# Created: 11/05/2014


import sys
#import unittest
import os
from multiprocessing import Pool
from multiprocessing.dummy import Pool as ThreadPool
import getopt
import logging
import shutil
import subprocess
#import uuid
import threading
import Queue
import time
import traceback

global basedir, tmpdir, arguments, segment_cutted_dir, segment_converted, segment_converted_dir, INPUT_FILE, SEG_TIME, IS_ERROR, DELETE, full_command, VIDEO_FORMAT, CRF
basedir = os.getcwd()
#tmpdir = './multi-encode-' + str(uuid.uuid4())
tmpdir = '.'
arguments = ''
segment_cutted_dir = tmpdir + '/segment_cutted_dir'
segment_converted = []
segment_converted_dir = tmpdir + '/segment_converted_dir'
INPUT_FILE = ''
SEG_TIME = 60
IS_ERROR = 0
DELETE = 1
CRF = 15
DRY_RUN = 0
queue_length = 10
full_command = ''
VIDEO_FORMAT = ''  #MPEG2
logging.basicConfig(level = logging.INFO)


#----------------------------------------------------------------------
def probe_file(filename):
    cmnd = ['ffprobe', '-show_format', '-pretty', '-loglevel', 'quiet', filename]
    p = subprocess.Popen(cmnd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #print filename
    out, err =  p.communicate()
    #print out
    if err:
        print err
        return None
    return out

#----------------------------------------------------------------------
def time_to_sec(time_raw):
    """str->int
    ignore .*."""
    hr = int(time_raw.split(':')[0]) * 3600
    minute = int(time_raw.split(':')[1]) * 60
    sec = int(float(time_raw.split(':')[2]))
    return int(hr + minute + sec)

#----------------------------------------------------------------------
def sec_to_time(sec_raw):
    """int->str"""
    hr = int(sec_raw / 3600)
    sec_raw = sec_raw - 3600 * hr
    minute = input(sec_raw / 60)
    sec = sec_raw - 60 * min
    return str(str(hr) + ':' + str(minute) + ':' + str(sec))

#----------------------------------------------------------------------
def get_file_time(filename):
    """str->int"""
    logging.info('Detecting video info...')
    try:
        for line in probe_file(filename).split('\n'):
            if 'duration' in line:
                video_duration = str(line.split('=')[1])
                return video_duration
    except:
        logging.fatal('Cannot read video file!')
        #shutil.rmtree(tmpdir)
        exit()

#----------------------------------------------------------------------
def get_extname(input_file):
    """"""
    return os.path.splitext(input_file)

#----------------------------------------------------------------------
def make_segment_list(input_file_length, step):
    """int,int->list
    must in sec!
    All the items in the list are starting time."""
    if input_file_length % step == 0:
        return [i * step for i in range(int(input_file_length / step))]
    else:
        return [i * step for i in range(int(input_file_length / step) + 1)]

#----------------------------------------------------------------------
def cut_one_segment(start_time, video_format = '', crf = 15, input_file = INPUT_FILE, step_time = SEG_TIME):
    """str,int,int,int-> None(File)
    start/stop time in sec, int.
    Input file should be readble by ffmpeg.
    In case the audio gives us trouble, the audio stream is disabled.
    TODO: use the same format as convert_one_segment()."""
    #start_time = sec_to_time(start_time)
    #All times can be in sec.
    #original_extname = get_extname(input_file)
    #Dont need since we will do a convert into loseless h264 format
    logging.info('Cutting original file piece, start at {start_time}...'.format(start_time = start_time))
    # Test shows that ffmpeg is able to handle the time
    if video_format == 'avc':
        command = 'ffmpeg -i {input_file} -c:v libx264 -an -preset ultrafast -crf {crf} -ss {start_time} -t {step_time} -y {segment_cutted_dir}/{start_time}.mp4'.format(input_file = input_file, start_time = start_time, step_time = step_time, segment_cutted_dir = segment_cutted_dir, crf = crf)
    else:
        command = 'ffmpeg -i {input_file} -f mpeg -q:v 0 -y  -an -ss {start_time} -t {step_time} {segment_cutted_dir}/{start_time}.mp4'.format(input_file = input_file, start_time = start_time, step_time = step_time, segment_cutted_dir = segment_cutted_dir)
    #print(command)
    if subprocess.call(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0:
        #If ffmpeg return no error
        #shutil.move()
        return start_time
    else:
        #ffmpeg exit with error
        #logging.warning('Segment cut failed! Start time at {start_time}'.format(start_time = start_time))
        return -1

#----------------------------------------------------------------------
def convert_one_segment(start_time, arguments, full_command = ''):
    """"int,str,str->None
    INPUT_SEGMENT_FILE, OUPUT_SEGMENT_FILE can be used in the full command line to reduce the difficutly.
    """
    logging.info('Converting original file piece, start at {start_time}...'.format(start_time = start_time))
    input_segment_file = '{segment_cutted_dir}/{start_time}.mp4'.format(segment_cutted_dir = segment_cutted_dir, start_time = start_time)
    ouput_segment_file = '{segment_converted_dir}/{start_time}_h264.mp4'.format(segment_converted_dir = segment_converted_dir, start_time = start_time)
    if full_command == '':
        command = 'ffmpeg -i {INPUT_SEGMENT_FILE} {arguments} -y {OUPUT_SEGMENT_FILE}'.format(INPUT_SEGMENT_FILE = input_segment_file, OUPUT_SEGMENT_FILE = ouput_segment_file, arguments = arguments)
    else:
        command = full_command.format(INPUT_SEGMENT_FILE = input_segment_file, OUPUT_SEGMENT_FILE = ouput_segment_file)
    #os.system('x264 -i {start_time}.mkv {arguments}'.format(arguments = arguments))
    if subprocess.call(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0:
        #If ffmpeg return no error
        #shutil.move()
        logging.info('Segment at {start_time} converted'.format(start_time = start_time))
        #segment_converted.append(start_time)
        if DELETE == 2:
            try:
                os.remove(input_segment_file)
            except:
                logging.warning('Cannot remove temp file!')
        return start_time
    else:
        #ffmpeg exit with error
        #logging.warning('Segment convert failed! Start time at {start_time}'.format(start_time = start_time))
        return -1

#----------------------------------------------------------------------
def concat_file(time_list = segment_converted, filename = 'video_to_convert'):
    """From: Biligrab"""
    os.chdir(basedir)
    f = open('ff.txt', 'w')
    ff = ''
    cwd = segment_converted_dir
    for i in segment_converted:
        ff = ff + 'file \'{cwd}/{i}_h264.mp4\'\n'.format(cwd = cwd, i = i)
    ff = ff.encode("utf8")
    f.write(ff)
    f.close()
    if DELETE > 0:
        try:
            shutil.rmtree(segment_cutted_dir)
        except:
            logging.warning('Cannot delete temp dir!')
    logging.info('Concating videos...')
    command = 'ffmpeg -f concat -i ff.txt -c copy "' + filename + '".mp4'
    if subprocess.call(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0:
        #If ffmpeg return no error
        #shutil.move()
        logging.info('Concated!')
    else:
        #ffmpeg exit with error
        logging.warning('Concat failed')

########################################################################
class CutVideo(threading.Thread):
    """Threaded Cut Video"""
    #----------------------------------------------------------------------
    def __init__(self, queue, out_queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.out_queue = out_queue
    
    #----------------------------------------------------------------------
    def run(self):
        while True:
            if out_queue.full():
                pass
            #grabs start time from queue
            start_time = self.queue.get()
            return_value = cut_one_segment(start_time, video_format=VIDEO_FORMAT, 
                                          input_file=INPUT_FILE, 
                                          step_time=SEG_TIME)
            if return_value == -1:
                global IS_ERROR
                #Error return code
                logging.warning('[*] Segment Slicing Failed: Start time {start_time}'.format(start_time = start_time))
                IS_ERROR += 1
            else:
                self.out_queue.put(return_value)
                pass
            #signals to queue job is done
            self.queue.task_done()

########################################################################
class ConvertThread(threading.Thread):
    """Threaded Cut Video"""
    #----------------------------------------------------------------------
    def __init__(self, out_queue):
        threading.Thread.__init__(self)
        self.out_queue = out_queue
        
    #----------------------------------------------------------------------
    def run(self):
        while True:
            #grabs time from queue
            start_time = self.out_queue.get()
            return_value = convert_one_segment(start_time, arguments = arguments, full_command = full_command)
            if return_value == -1:
                #Error return code
                logging.warning('[*] Segment Convertion Failed: Start time {start_time}'.format(start_time = start_time))
                IS_ERROR += 1
            else:
                segment_converted.append(start_time)
                pass
            self.out_queue.task_done()

#----------------------------------------------------------------------
def main(INPUT_FILE, slicer_thread = 3, converter_thread = 3, DRY_RUN = 0):
    """"""
    try:
        os.mkdir(segment_converted_dir)
        os.mkdir(segment_cutted_dir)
    except:
        pass
    start = time.time()
    logging.info('Probing the file...')
    input_file_length = time_to_sec(get_file_time(INPUT_FILE))
    start_time_list = make_segment_list(input_file_length, SEG_TIME)
    if DRY_RUN != 0:
        logging.info('DRY RUN!')
        start_time_list = start_time_list[:DRY_RUN]
    logging.info('Start threading!')
    global queue
    global out_queue
    queue = Queue.Queue()
    out_queue = Queue.Queue(int(queue_length))
    main_threading(start_time_list=start_time_list, slicer_thread=slicer_thread, 
                  converter_thread=slicer_thread)
    queue.join()
    out_queue.join()
    if sorted(segment_converted) != start_time_list:
        logging.fatal('Queue ERROR!')
        exit()
    else:
        concat_file(time_list=segment_converted, filename = os.path.basename(INPUT_FILE).split('.')[0] + '_converted')
    logging.info('DONE!')
    print("Elapsed Time: %s" % (time.time() - start))
    if DELETE > 0:
        try:
            shutil.rmtree(segment_converted_dir)
            shutil.rmtree(segment_cutted_dir)
            os.remove('ff.txt')
        except:
            pass

#----------------------------------------------------------------------
def main_threading(start_time_list = [], slicer_thread = 3, converter_thread = 3):
    """"""
    #spawn a pool of threads, and pass them queue instance
    for i in range(int(slicer_thread)):
        t = CutVideo(queue, out_queue)
        t.setDaemon(True)
        t.start()
    for i in range(int(converter_thread)):
        dt = ConvertThread(out_queue)
        dt.setDaemon(True)
        dt.start()
    #populate queue with data
    for start_time in start_time_list:
        queue.put(start_time)
    #wait on the queue until everything has been processed
    queue.join()
    out_queue.join()

#----------------------------------------------------------------------
def usage():
    """"""
    print('''
    Parallel-Transcode
        
    https://github.com/cnbeining/parallel-transcode
    http://www.cnbeining.com/
    
    Beining@ACICFG
    
    
    Usage:
    
    python multi-ffmpeg.py (-h/help) (-i/input-file) (-s/slicer)
                           (-c/converter) (-q/queue-length)
                           (-a/arguments) (-f/full-command)
                           (-d/delete-temp) (-v/video-format)
                           (-r/dry-run)
    
    -h: Default: None
        Print this usage file.
    
    -i: Default: None
        The input file.
        Please make sure it can be read by ffmpeg.
        
    -s: Default: 3
        The thread number of Slicer that cut the file into loseless pieces.
    
    -c: Default: 3 
        The thread number of Converter that convert the file into pieces.
        
    -q: Default: 10
        Max pieces to control cache size.
        Wrongly set may lead to dramatic decrease of speed or running out of space!
    
    -a: Default: None
        The arguments you want to pass to ffmpeg when encoding.
        
    -f: Default: None
        In case you want something special, just input whatever command you want here!
        To make sure the command can be read,
        use {INPUT_SEGMENT_FILE}, {OUPUT_SEGMENT_FILE} in the command line.
        
    -d: Default: 1
        If set to 0, Parallel-Transcode will not delete any temporary files.
        1: Only delete at the end of stage.
        2: Delete on the fly.
            
    -t: Default: 30
        The time of one segment in sec.
        
    -v: Default: (Blank)
        The temporary file's format.
        If set to "avc", Parallel-Transcode will use a *loseless* way to transcode file to reserve its quality.
        It not set, the temporary file would be in MPEG2, same quality. There's no guarantee that this is loseless.
        
    -r: Default: 15
        Used with "-v avc".
        The crf to use when convert.
        0 for loseless.
    
    -n: Default: 0
        Dry run.
        Convert first N piece to test whether the script is running properly.
''')

#----------------------------------------------------------------------
if __name__=='__main__':
    argv_list = sys.argv[1:]
    try:
        opts, args = getopt.getopt(argv_list, "hi:s:c:q:t:a:f:d:v:r:n:",
                                   ['help', "input-file=", 'slicer=', 'converter=', 'queue-length=', 'segment-time=', 'arguments=', 'full-command=', 'delete-temp=', 'video-format=', 'crf=', 'dry-run='])
    except getopt.GetoptError:
        usage()
        exit()
    for o, a in opts:
        if o in ('-h', '--help'):
            usage()
            exit()
        if o in ('-i', '--input-file'):
            INPUT_FILE = a
        if o in ('-s', '--slicer'):
            slicer_thread = int(a)
        if o in ('-c', '--converter'):
            converter_thread = int(a)
        if o in ('-q', '--queue-length'):
            queue_length = int(a)
        if o in ('-t', '--segment-time'):
            SEG_TIME = int(a)
        if o in ('-a', '--arguments'):
            arguments = a
        if o in ('-f', '--full-command'):
            full_command = a
        if o in ('-d', '--delete-temp'):
            DELETE = int(a)
        if o in ('-v', '--video-format'):
            VIDEO_FORMAT = a
        if o in ('-r', '--delete-temp'):
            CRF = int(a)
        if o in ('-n', '--dry-run'):
            DRY_RUN = int(a)
    main(INPUT_FILE, slicer_thread=slicer_thread, 
            converter_thread=converter_thread, DRY_RUN = DRY_RUN)
