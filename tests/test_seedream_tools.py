import base64
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from PIL import Image
from Department.视觉设计部.xiaoha import openrouter_image_site as site
from Department.视觉设计部.xiaoha.features import seedream_tools as tools


def png(size=(800, 600), color='white', mode='RGB'):
    output = io.BytesIO()
    Image.new(mode, size, color).save(output, 'PNG')
    return output.getvalue()


def upload(raw=None):
    return {'data': raw or png(), 'name': 'source.png', 'type': 'image/png'}


class SeedreamToolsTests(unittest.TestCase):
    def test_region_only_requirements_can_submit_without_global_notes(self):
        marks=[{'type':'rect','points':[[100,200],[800,900]]}]
        for mode in ['seedream_coordinate_edit','seedream_mark_edit']:
            prompt=tools.compose_edit_prompt(mode,'',marks,{'0':'将背景换成浅蓝色'})
            self.assertIn('将背景换成浅蓝色',prompt)
        with self.assertRaises(ValueError):
            tools.compose_edit_prompt('seedream_coordinate_edit','',marks,{})

    def test_background_dispatch_preserves_specialized_parameters(self):
        feature=site.get_feature_by_key('seedream_layers')
        context={'feature':feature,'model':site.ARK_SEEDREAM_5_PRO_MODEL,'output_mode':'image','max_output_images':1,
                 'uploaded_files':[upload()],'prompt':'','seedream_options':{'size':'auto'}}
        expected={'images':['saved.png'],'layers':[{'z_index':0}]}
        with patch.object(tools,'run_job',return_value=expected) as run,patch.object(site,'finalize_feature_job_result',side_effect=lambda context,result,job_id:result):
            self.assertEqual(site.run_feature_job(context),expected)
        self.assertEqual(run.call_args.args[1]['seedream_options'],{'size':'auto'})

    def test_all_three_tools_are_visible_and_grouped(self):
        visible = {feature['key'] for feature in site.get_visible_features()}
        self.assertTrue(set(tools.FEATURE_KEYS).issubset(visible))
        self.assertTrue(any(set(tools.FEATURE_KEYS).issubset(keys) for _, keys in site.SIDE_MENU_FEATURE_GROUPS))

    def test_coordinate_prompt_uses_normalized_tags_and_per_region_instructions(self):
        marks = [{'type': 'rect', 'points': [[800, 900], [100, 200]]}, {'type': 'point', 'points': [[999, 0]]}]
        text = tools.compose_edit_prompt('seedream_coordinate_edit', '背景换成蓝色', marks, {'0': '保留文字'})
        self.assertIn('图1<bbox>100 200 800 900</bbox>', text)
        self.assertIn('<point>999 0</point>', text)
        self.assertIn('保留文字', text)

    def test_invalid_coordinates_rejected(self):
        for mark in [{'type':'rect','points':[[0,0],[0,20]]}, {'type':'point','points':[[1000,0]]},
                     {'type':'point','points':[[float('nan'),0]]}, {'type':'arrow','points':[[0,0],[20,30]]}]:
            with self.subTest(mark=mark), self.assertRaises(ValueError):
                tools.validate_marks([mark], coordinates=True)

    def test_marker_image_contains_actual_drawings_without_mutating_original(self):
        original = png()
        marks = [{'type':'arrow','points':[[100,100],[600,600]]}, {'type':'ellipse','points':[[300,300],[700,700]]},
                 {'type':'brush','points':[[0,0],[20,60],[100,100]]}]
        marked = tools.annotated_input(original, marks)
        with Image.open(io.BytesIO(marked['data'])) as image:
            self.assertEqual(image.size, (800,600))
            self.assertEqual(image.getpixel((160,120)), (255,48,48))
        self.assertNotEqual(marked['data'], original)
        self.assertEqual(original, png())

    def test_layer_request_preserves_all_metadata_and_accepts_auto_size(self):
        response = Mock(status_code=200, headers={'x-request-id': 'request-123'})
        response.json.return_value = {'data': [
            {'url':'https://test/base.jpg','output_format':'jpeg','z_index':0,'size':'800x600'},
            {'url':'https://test/layer.png','output_format':'png','z_index':1,'size':'200x100',
             'bounding_box':{'absolute':[10,20,210,120],'normalized':[12,33,262,200]},'name':'商品','description':'商品主体'}],
             'usage':{'generated_images':2,'total_tokens':100}}
        with patch.object(site,'load_ark_api_key',return_value='test-key'),patch.object(site.requests,'post',return_value=response) as post:
            result = site.call_ark_seedream_images_api('',[upload()],size='auto',layer_decomposition=True,
                                                     output_format='jpeg',optimize_prompt_mode='fast',watermark=False)
        payload=post.call_args.kwargs['json']
        self.assertTrue(payload['layer_decomposition'])
        self.assertEqual(payload['prompt'],'')
        self.assertEqual(payload['size'],'auto')
        self.assertEqual(payload['optimize_prompt_options'],{'mode':'fast'})
        self.assertFalse(payload['watermark'])
        self.assertEqual(result['layers'][1]['bounding_box']['absolute'],[10,20,210,120])
        self.assertEqual(result['layers'][1]['name'],'商品')
        self.assertEqual(result['request_id'],'request-123')
        self.assertEqual(result['usage']['generated_images'],2)

    def test_invalid_layer_combinations_fail_before_network(self):
        for files, options in [([],{}),([upload(),upload()],{}),([upload()],{'background':'transparent'}),
                               ([upload()],{'size':'2048x2048'}),([upload(png((100,100)))],{})]:
            with self.subTest(options=options),patch.object(site,'load_ark_api_key',return_value='test'),patch.object(site.requests,'post') as post:
                with self.assertRaises(ValueError):
                    site.call_ark_seedream_images_api('',files,layer_decomposition=True,**options)
                post.assert_not_called()

    def test_layer_item_error_is_not_silently_dropped(self):
        response=Mock(status_code=200)
        response.json.return_value={'data':[{'url':'https://test/base.png','z_index':0},{'error':{'message':'failed'}}]}
        with patch.object(site,'load_ark_api_key',return_value='test'),patch.object(site.requests,'post',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'处理失败'):
                site.call_ark_seedream_images_api('',[upload()],layer_decomposition=True)

    def test_base64_format_matches_jpeg_metadata(self):
        response=Mock(status_code=200)
        response.json.return_value={'data':[{'b64_json':'YWJj','output_format':'jpeg'}]}
        with patch.object(site,'load_ark_api_key',return_value='test'),patch.object(site.requests,'post',return_value=response):
            result=site.call_ark_seedream_images_api('edit',[upload()],response_format='b64_json',output_format='jpeg',interactive_edit=True)
        self.assertEqual(result['images'],['data:image/jpeg;base64,YWJj'])

    def test_transparency_requires_alpha_input_and_png(self):
        with patch.object(site,'load_ark_api_key',return_value='test'),patch.object(site.requests,'post') as post:
            with self.assertRaises(ValueError):
                site.call_ark_seedream_images_api('edit',[upload()],output_format='png',background='transparent')
            with self.assertRaises(ValueError):
                site.call_ark_seedream_images_api('edit',[upload(png(mode='RGBA'))],output_format='jpeg',background='transparent')
            post.assert_not_called()

    def test_archive_preserves_alpha_bytes_and_composite_positions(self):
        raw_base=png((800,600))
        raw_layer=png((80,60),(255,0,0,128),'RGBA')
        assets={'base':raw_base,'layer':raw_layer}
        result={'images':['base','layer'],'layers':[
            {'source':'layer','z_index':1,'name':'../商品','bounding_box':{'absolute':[100,100,180,160]}},
            {'source':'base','z_index':0}], 'usage':{'generated_images':2},'model':site.ARK_SEEDREAM_5_PRO_MODEL}
        with tempfile.TemporaryDirectory() as directory:
            api=SimpleNamespace(ensure_feature_output_dir=lambda key:Path(directory),load_image_bytes_from_url=lambda source:(assets[source],'image/png'))
            saved=tools.persist_result(api,{'feature':{'key':'seedream_layers'},'account_name':'alice'},result)
            folder=Path(saved['seedream_artifact_dir'])
            self.assertEqual(Path(saved['layers'][1]['source']).read_bytes(),raw_layer)
            composite=tools.composite_layers(saved['layers'])
            self.assertEqual(composite.getpixel((0,0)),(255,255,255,255))
            self.assertEqual(composite.getpixel((110,110)),(255,127,127,255))
            self.assertEqual(tools.composite_layers(saved['layers'],[]).getpixel((110,110)),(255,255,255,255))
            with zipfile.ZipFile(folder/'layers.zip') as archive:
                self.assertIn('manifest.json',archive.namelist())
                self.assertEqual(archive.read('01_layer.png'),raw_layer)
                self.assertNotIn('../商品',archive.namelist())
                manifest=json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['layers'][1]['bounding_box']['absolute'],[100,100,180,160])
            self.assertTrue((folder/'result.json').is_file())
            self.assertNotEqual(tools.result_directory(api,'alice'),tools.result_directory(api,'bob'))

    def test_worker_sends_original_and_annotated_reference_once(self):
        api=SimpleNamespace(normalize_uploaded_input=site.normalize_uploaded_input,call_ark_seedream_images_api=Mock(return_value={'images':['ok']}))
        context={'feature':{'key':'seedream_mark_edit'},'uploaded_files':[upload()], 'prompt':'替换箭头指向的商品',
                 'seedream_marks':[{'type':'arrow','points':[[10,10],[500,500]]}], 'seedream_options':{'size':'1.5K'}}
        with patch.object(tools,'persist_result',side_effect=lambda api,context,result:result):
            tools.run_job(api,context)
        call=api.call_ark_seedream_images_api.call_args
        self.assertEqual(len(call.args[1]),2)
        self.assertNotEqual(call.args[1][0]['data'],call.args[1][1]['data'])
        self.assertIn('图1是原图',call.args[0])
        self.assertTrue(call.kwargs['interactive_edit'])
        self.assertEqual(call.kwargs['size'],'1.5K')
        api.call_ark_seedream_images_api.assert_called_once()

    def test_worker_supports_already_marked_upload_without_extra_reference(self):
        api=SimpleNamespace(normalize_uploaded_input=site.normalize_uploaded_input,call_ark_seedream_images_api=Mock(return_value={'images':['ok']}))
        with patch.object(tools,'persist_result',side_effect=lambda api,context,result:result):
            tools.run_job(api,{'feature':{'key':'seedream_mark_edit'},'uploaded_files':[upload()], 'prompt':'替换红框区域'})
        self.assertEqual(len(api.call_ark_seedream_images_api.call_args.args[1]),1)

    def test_missing_bbox_retains_all_downloadable_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            api=SimpleNamespace(ensure_feature_output_dir=lambda key:Path(directory),load_image_bytes_from_url=lambda source:(png(),'image/png'))
            result=tools.persist_result(api,{'feature':{'key':'seedream_layers'}},{'images':['base','layer'],'layers':[{'source':'base','z_index':0},{'source':'layer','z_index':1}]})
            self.assertIn('composite_error',result)
            self.assertTrue((Path(result['seedream_artifact_dir'])/'layers.zip').is_file())


if __name__=='__main__':
    unittest.main()
