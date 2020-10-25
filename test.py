import os
import cv2
import time
import keras
import argparse
import PIL.Image
import numpy as np
import tensorflow as tf
import prettytable as pt

"""
Attack on Attention (AoA)
Universal Adversarial Attack on Attention and the Resulting Dataset DAmageNet, IEEE TPAMI, 2020
https://ieeexplore.ieee.org/document/9238430
Sizhe Chen, Zhengbao He, Chengjin Sun, Jie Yang, Xiaolin Huang*
e-mails: {sizhe.chen, lstefanie, sunchengjin, jieyang, xiaolinhuang}@sjtu.edu.cn
Institute of Image Processing and Pattern Recognition, Shanghai Jiao Tong University

Description
This is a script to test the top-1 error rate of pretrained models in DAmageNet / ImageNet validation set.
DAmageNet is a massive dataset containing 50000 universal adversarial samples generated by SI-AoA.
DAmageNet could be downloaded in http://www.pami.sjtu.edu.cn/Show/56/122.

Environment
    ! python==3.7.3
    ! tensorflow==1.13.1
    ! keras==2.2.4
    scipy==1.2.1
    numpy==1.16.5
    pillow==6.2.1
    opencv-python==4.1.2
    prettytable==0.7.2
    argparse==1.4.0

Usage
    Command
    python test.py [dataset_path] [net_list] [gpu_id]
    
    Test in DAmageNet for VGG19,ResNet50,DenseNet121 in GPU 0:
    python test.py ./DAmageNet VGG19,ResNet50,DenseNet121 0
    
    Test in ImageNet validation set for VGG19 in GPU 1:
    python test.py ./ILSVRC2012_img_val VGG19 1

    Valid networks:
    ResNet50, ResNet101, ResNet152, InceptionResNet, InceptionV3, Xception, VGG16, VGG19
    DenseNet121, DenseNet169, DenseNet201, NASNetMobile, NASNetLarge
"""

def process_sample(sample_path:str, return_size:int):
    """
    Load the image in np.float32 of [0, 255] as [return_size, return_size, 3]
    Image is centrally cropped and resized
    """
    sample = PIL.Image.open(sample_path).convert('RGB')
    size, large_size, index = np.min(sample.size), np.max(sample.size), np.argmin(sample.size)
    if index: # long
        sample = sample.resize((int(return_size/size*large_size), return_size))
        cut_up, cut_down = int((np.max(sample.size) + return_size) / 2), int((np.max(sample.size) - return_size) / 2)
        sample = np.array(sample)[:, cut_down:cut_up, :] #sample.size = (a, b) -> np.array(sample).shape = (b, a, 3)
    else: # wide
        sample = sample.resize((return_size, int(return_size/size*large_size)))
        cut_up, cut_down = int((np.max(sample.size) + return_size) / 2), int((np.max(sample.size) - return_size) / 2)
        sample = np.array(sample)[cut_down:cut_up, :, :]
    
    sample = cv2.resize(sample, (return_size, return_size))
    return np.clip(sample.astype(np.float32), 0, 255)

def crop_or_pad(sample:np.ndarray, size:int):
    """
    Crop or pad the sample into [size, size, 3] without resizing
    The adversarial sample should be processed with this function because resizing decreases their aggression
    """
    img = PIL.Image.fromarray(sample.astype(np.uint8))
    if img.size[0] > size:
        img = img.crop(((img.size[0] - size) / 2, (img.size[1] - size) / 2, (img.size[0] + size) / 2, (img.size[1] + size) / 2))
        img = img.resize((size, size))
    else:
        black = PIL.Image.fromarray(np.zeros((size, size, 3), dtype=np.uint8))
        black.paste(img, (int((size - img.size[0]) / 2), int((size - img.size[1]) / 2)))
        img = black
    return np.array(img)

def convert_second_to_time(sec:float):
    """
    Convert seconds into hour:minute:second
    """
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return "%02d:%02d:%02d" % (h, m, s)

def load_net_info(net_name:str, inp=None):
    """
    if inp is not None: load the network input size and preprocessing function
    else:               load the network model      and preprocessing function
    """
    size = {'InceptionV3': 299, 'Xception': 299, 'NASNetLarge': 331}.get(net_name, 224)
    if   net_name == 'ResNet50':        from keras.applications.resnet50            import ResNet50, preprocess_input;          net = ResNet50(input_tensor=inp)    if inp is not None else size
    elif net_name == 'ResNet101':       from keras_applications.resnet_v2           import ResNet101V2, preprocess_input;       net = ResNet101V2(input_tensor=inp, backend=keras.backend, layers=keras.layers, models=keras.models, utils=keras.utils)       if inp is not None else size
    elif net_name == 'ResNet152':       from keras_applications.resnet_v2           import ResNet152V2, preprocess_input;       net = ResNet152V2(input_tensor=inp, backend=keras.backend, layers=keras.layers, models=keras.models, utils=keras.utils)       if inp is not None else size
    elif net_name == 'InceptionResNetV2': from keras_applications.inception_resnet_v2 import InceptionResNetV2, preprocess_input; net = InceptionResNetV2(input_tensor=inp, backend=keras.backend, layers=keras.layers, models=keras.models, utils=keras.utils) if inp is not None else size
    elif net_name == 'InceptionV3':     from keras.applications.inception_v3        import InceptionV3, preprocess_input;       net = InceptionV3(input_tensor=inp) if inp is not None else size
    elif net_name == 'Xception':        from keras.applications.xception            import Xception, preprocess_input;          net = Xception(input_tensor=inp)    if inp is not None else size
    elif net_name == 'VGG16':           from keras.applications.vgg16               import VGG16, preprocess_input;             net = VGG16(input_tensor=inp)       if inp is not None else size
    elif net_name == 'VGG19':           from keras.applications.vgg19               import VGG19, preprocess_input;             net = VGG19(input_tensor=inp)       if inp is not None else size
    elif net_name == 'DenseNet121':     from keras.applications.densenet            import DenseNet121, preprocess_input;       net = DenseNet121(input_tensor=inp) if inp is not None else size
    elif net_name == 'DenseNet169':     from keras.applications.densenet            import DenseNet169, preprocess_input;       net = DenseNet169(input_tensor=inp) if inp is not None else size
    elif net_name == 'DenseNet201':     from keras.applications.densenet            import DenseNet201, preprocess_input;       net = DenseNet201(input_tensor=inp) if inp is not None else size
    elif net_name == 'NASNetMobile':    from keras.applications.nasnet              import NASNetMobile, preprocess_input;      net = NASNetMobile(input_tensor=inp)if inp is not None else size
    elif net_name == 'NASNetLarge':     from keras.applications.nasnet              import NASNetLarge, preprocess_input;       net = NASNetLarge(input_tensor=inp) if inp is not None else size
    else: raise ValueError('Invalid Network Name')
    return net, preprocess_input

def build(net_list:list):
    """
    Build all networks in net_list, return sess and dicts
    feed inputs[net_name] with image of size[net_name], run sess, get output[net_name] (None, 1000)
    """
    sess = tf.InteractiveSession()
    inputs, outputs, size = {}, {}, {} # record variables in dict
    for n in net_list:
        print('Loading', n)
        size[n], pre_pro = load_net_info(n) # load size and preprocessing function
        inputs[n] = tf.placeholder(tf.float32, [1, size[n], size[n], 3], name=n)
        net, _  = load_net_info(n, pre_pro(inputs[n], backend=keras.backend, layers=keras.layers, models=keras.models, utils=keras.utils))
        outputs[n] = net.output
    return sess, inputs, outputs, size

def get_label(form:str):
    """
    Load the labels for 50000 samples
    """
    labels = {}
    with open('val.txt', 'r') as f: label_list = f.read().replace('.JPEG', form).split('\n')
    for item in label_list: 
        if item == '': continue
        item = item.split(' ')
        labels[item[0]] = int(item[1])
    return labels

def judge_pred(image_path, net_name, label, sess, inputs, outputs, size):
    """
    Judge whether the network is wrong
    """
    image = process_sample(image_path, 224)
    prd = np.argmax(sess.run(outputs[net_name], {inputs[net_name]: [crop_or_pad(image, size[net_name])]})[0])
    return prd != label

def print_result(log):
    """
    Print the final results in a table
    """
    print('\n')
    tb = pt.PrettyTable()
    tb.field_names = ["Network", "Top-1 Error"]
    for net in net_list: tb.add_row([net, '%.2f' % (sum(log[net]) / len(log[net]) * 100) + '%'])
    print(tb)

def test(dataset, net_list, **kwargs):
    """
    Test the error rate of networks in net_list on the samples in dataset
    """
    labels = get_label(form=os.path.splitext(os.listdir(dataset)[0])[1])
    log = {}
    for net in net_list: log[net] = []
    num_samples = len(os.listdir(dataset))
    start = time.time()
    print('\nTest', net_list, 'on', dataset, 'for', num_samples, 'samples')

    # test each sample
    for i, file in enumerate(os.listdir(dataset)):
        err_str = ''
        for net_name in net_list: 
            do_error = judge_pred(dataset + '/' + file, net_name, labels[file], **kwargs)
            log[net_name].append(do_error)
            err_str += '%.2f' % (sum(log[net_name]) / len(log[net_name]) * 100) + '% '
        print('[ Sample %d/%d ] [ Error %s ] [ TimeRemain %s ]' %  
            (i+1, num_samples, err_str, convert_second_to_time((time.time() - start) / (i+1) * (num_samples - i))), end='\r')
    print_result(log)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test DAmageNet or ImageNet validation set', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('dataset',  help='Dataset directory, DAmageNet or ILSVRC2012_img_val')
    parser.add_argument('net_list', help='all networks to be tested, split with comma but without space')
    parser.add_argument('gpu_id',   help='GPU(s) used')
    args, _ = parser.parse_known_args()
    assert os.path.exists(args.dataset) and os.path.exists('val.txt')
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_id
    
    net_list = args.net_list.split(',')
    net_list.sort() # DenseNets should be loaded first
    sess, inputs, outputs, size = build(net_list)
    test(args.dataset, net_list, sess=sess, inputs=inputs, outputs=outputs, size=size)