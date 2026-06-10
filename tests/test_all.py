"""
Все тесты в одном файле.
Запуск: python -m pytest tests/test_all.py -v
"""

import sys
import os
import json
import tempfile
import re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nextt.core.normalizer import SpecNormalizer, ParsedRadiator



# ======================================================================
# ТЕСТЫ ДЛЯ SPECNORMALIZER (27 тестов)
# ======================================================================

class TestKermi:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_kermi_ftv_11_500_1200(self):
        r = self.n.normalize_and_extract("Kermi FTV 11 500/1200")
        assert r.recognized is True
        assert r.rad_type == "11"
        assert r.height == 500
        assert r.length == 1200
        assert r.connection == "VK-правое"
    
    def test_kermi_ftv_22_600_1400_ra(self):
        r = self.n.normalize_and_extract("Kermi FTV 22 600/1400 ra")
        assert r.recognized is True
        assert r.rad_type == "22"
        assert r.height == 600
        assert r.length == 1400
    
    def test_kermi_fk0_22_600_1400(self):
        r = self.n.normalize_and_extract("Kermi FK0 22 600/1400")
        assert r.recognized is True
        assert r.rad_type == "22"
        assert r.connection == "K-боковое"
    
    def test_kermi_type12_converts_to_21(self):
        r = self.n.normalize_and_extract("Kermi FTV 12 500/1200")
        if r.recognized:
            assert r.rad_type == "21"


class TestPurmo:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_purmo_compact_22_600_1400(self):
        r = self.n.normalize_and_extract("Purmo Compact 22 600/1400")
        assert r.recognized is True
        assert r.rad_type == "22"
        assert r.height == 600
        assert r.length == 1400
    
    def test_purmo_ventil_11_500_1200(self):
        r = self.n.normalize_and_extract("Purmo Ventil 11 500/1200")
        assert r.recognized is True
        assert r.rad_type == "11"


class TestEvra:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_evra_c22_500_800(self):
        r = self.n.normalize_and_extract("EVRA C22-500-800")
        assert r.recognized is True
        assert r.rad_type == "22"
        assert r.height == 500
        assert r.length == 800
        assert r.connection == "K-боковое"
    
    def test_evra_cv22_500_800(self):
        r = self.n.normalize_and_extract("EVRA CV22-500-800")
        assert r.recognized is True
        assert r.connection == "VK-правое"
    
    def test_evra_h10_30_400(self):
        r = self.n.normalize_and_extract("EVRA H10-30-400")
        if r.recognized:
            assert r.rad_type == "10"
            assert r.height == 300


class TestLidea:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_lidea_lk_11_504(self):
        r = self.n.normalize_and_extract("ЛК 11-504")
        if r.recognized:
            assert r.rad_type == "11"
            assert r.height == 500
            assert r.length == 400
            assert r.connection == "K-боковое"
    
    def test_lidea_lu_22_516(self):
        r = self.n.normalize_and_extract("ЛУ 22-516")
        if r.recognized:
            assert r.rad_type == "22"
            assert r.connection == "VK-правое"


class TestOasis:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_oasis_pn_22_4_05(self):
        r = self.n.normalize_and_extract("Oasis PN 22-4-05")
        if r.recognized:
            assert r.rad_type == "22"
            assert r.height == 400
            assert r.length == 500
    
    def test_oasis_ov_11_3_12(self):
        r = self.n.normalize_and_extract("Oasis OV 11-3-12")
        if r.recognized:
            assert r.rad_type == "11"
            assert r.height == 300
            assert r.length == 1200
            assert r.connection == "VK-правое"


class TestUniversalFormats:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_triplet_with_dash(self):
        r = self.n.normalize_and_extract("22-400-1000")
        assert r.recognized is True
        assert r.rad_type == "22"
        assert r.height == 400
        assert r.length == 1000
    
    def test_triplet_with_slash(self):
        r = self.n.normalize_and_extract("11/500/800")
        assert r.recognized is True
        assert r.rad_type == "11"
        assert r.height == 500
        assert r.length == 800
    
    def test_triplet_with_x(self):
        r = self.n.normalize_and_extract("33 x 600 x 700")
        assert r.recognized is True
        assert r.rad_type == "33"
        assert r.height == 600
        assert r.length == 700
    
    def test_coded_triplet_11_03_18(self):
        r = self.n.normalize_and_extract("11-03-18")
        if r.recognized:
            assert r.rad_type == "11"
            assert r.height == 300
            assert r.length == 1800
    
    def test_vk_profil_with_side(self):
        r = self.n.normalize_and_extract("VK-Profil 22-03-12 la")
        if r.recognized:
            assert r.rad_type == "22"
            assert r.connection == "VK-левое"


class TestEdgeCases:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_empty_string(self):
        r = self.n.normalize_and_extract("")
        assert r.recognized is False
    
    def test_none_value(self):
        r = self.n.normalize_and_extract(None)
        assert r.recognized is False
    
    def test_short_text(self):
        r = self.n.normalize_and_extract("радиатор")
        assert r.recognized is False
    
    def test_extra_spaces(self):
        r = self.n.normalize_and_extract("Kermi  FTV   11   500/1200")
        assert r.recognized is True
        assert r.rad_type == "11"
        assert r.height == 500
    
    def test_case_insensitive(self):
        lower = self.n.normalize_and_extract("kermi ftv 11 500/1200")
        upper = self.n.normalize_and_extract("KERMI FTV 11 500/1200")
        assert lower.rad_type == upper.rad_type
    
    def test_full_spec_line(self):
        text = "Радиатор стальной панельный Kermi FTV 11 500/1200, нижнее подключение, правая сторона, 2 шт."
        r = self.n.normalize_and_extract(text)
        if r.recognized:
            assert r.rad_type == "11"
            assert r.height == 500
            assert r.length == 1200


class TestArbonia:
    def setup_method(self):
        self.n = SpecNormalizer(debug=False)
    
    def test_arbonia_ftv_type12_left(self):
        r = self.n.normalize_and_extract(
            "Стальной панельный радиатор Arbonia FTV тип 12, 300x64x400 мм, RAL 9016, 10 бар, вентиль слева"
        )
        assert r.recognized is True
        assert r.rad_type == "21"
        assert r.height == 300
        assert r.length == 400
        assert r.connection == "VK-левое"
    
    def test_arbonia_ftv_type12_right(self):
        r = self.n.normalize_and_extract(
            "Стальной панельный радиатор Arbonia FTV тип 12, 500x64x1000 мм, RAL 9016, 10 бар, вентиль справа"
        )
        assert r.recognized is True
        assert r.rad_type == "21"
        assert r.height == 500
        assert r.length == 1000
        assert r.connection == "VK-правое"
    
    def test_arbonia_ftv_type22(self):
        r = self.n.normalize_and_extract(
            "Стальной панельный радиатор Arbonia FTV тип 22, 500x100x700 мм, RAL 9016, 10 бар, вентиль слева"
        )
        assert r.recognized is True
        assert r.rad_type == "22"
        assert r.height == 500
        assert r.length == 700
        assert r.connection == "VK-левое"


# ======================================================================
# ТЕСТЫ ДЛЯ PATTERNMANAGER (9 тестов)
# ======================================================================

class TestPatternManager:
    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.temp_file.close()
        self.patterns_path = self.temp_file.name
    
    def teardown_method(self):
        if os.path.exists(self.patterns_path):
            os.unlink(self.patterns_path)
    
    def create_manager(self):
        return PatternManager(patterns_file=self.patterns_path)
    
    def test_empty_patterns_file(self):
        manager = self.create_manager()
        assert manager.count == 0
        match = manager.find_match("Kermi FTV 11 500/1200")
        assert match is None
    
    def test_save_and_load_single_pattern(self):
        manager1 = self.create_manager()
        manager1.learn("Kermi FTV 11 500/1200", "VK-правое", "11", 500, 1200)
        assert manager1.count == 1
        manager1.save()
        
        manager2 = self.create_manager()
        assert manager2.count == 1
        match = manager2.find_match("Kermi FTV 11 500/1200")
        assert match is not None
        assert match["height"] == 500
    
    def test_pattern_applies_to_similar_names(self):
        manager = self.create_manager()
        manager.learn("Kermi FTV 11 500/1200", "VK-правое", "11", 500, 1200)
        
        test_names = [
            "Kermi FTV 11 500/1200 ra",
            "Kermi FTV 11 500/1200 RAL 9016",
            "Радиатор Kermi FTV 11 500/1200",
        ]
        
        for name in test_names:
            match = manager.find_match(name)
            assert match is not None, f"Не распознано: {name}"
    
    def test_multiple_patterns_best_match(self):
        manager = self.create_manager()
        manager.learn("Kermi 11 500/1200", "VK-правое", "11", 500, 1200)
        manager.learn("Kermi 22 600/1400", "K-боковое", "22", 600, 1400)
        
        assert manager.count == 2
        
        match1 = manager.find_match("Kermi 11 500/1200")
        assert match1["rad_type"] == "11"
        assert match1["height"] == 500
        
        match2 = manager.find_match("Kermi 22 600/1400")
        assert match2["rad_type"] == "22"
        assert match2["height"] == 600
    
    def test_learning_updates_existing_pattern(self):
        manager = self.create_manager()
        manager.learn("Kermi FTV 11 500/1200", "VK-правое", "11", 500, 1200)
        manager.learn("Kermi FTV 11 500/1200", "VK-правое", "11", 600, 1400)
        
        assert manager.count == 1
        match = manager.find_match("Kermi FTV 11 500/1200")
        assert match["height"] == 600
    
    def test_json_structure_is_valid(self):
        manager = self.create_manager()
        manager.learn("Test Radiator 500/1200", "VK-правое", "22", 500, 1200)
        manager.save()
    
        with open(self.patterns_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    
        assert isinstance(data, list)
        assert len(data) == 1
        pattern = data[0]
        # Было: assert "pattern" in pattern
        assert "original_name" in pattern  # ИСПРАВЛЕНО
        assert "connection" in pattern
        assert "rad_type" in pattern
        assert "height" in pattern
        assert "length" in pattern
    
    def test_load_corrupted_json(self):
        with open(self.patterns_path, 'w', encoding='utf-8') as f:
            f.write('{invalid json}!!!')
        
        manager = self.create_manager()
        assert manager.count == 0
        match = manager.find_match("Any name")
        assert match is None


class TestPatternManagerIntegration:
    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.temp_file.close()
        self.patterns_path = self.temp_file.name
    
    def teardown_method(self):
        if os.path.exists(self.patterns_path):
            os.unlink(self.patterns_path)
    
    def test_pattern_overrides_normalizer(self):
        from nextt.core.normalizer import SpecNormalizer
        
        manager = PatternManager(patterns_file=self.patterns_path)
        manager.learn("Kermi FTV 11 500/1200", "VK-правое", "33", 900, 3000)
        manager.save()
        
        manager2 = PatternManager(patterns_file=self.patterns_path)
        match = manager2.find_match("Kermi FTV 11 500/1200")
        
        assert match is not None
        assert match["rad_type"] == "33", "Должен использовать тип из паттерна!"
        assert match["height"] == 900
        assert match["length"] == 3000
    
    def test_pattern_with_named_groups(self):
        manager = PatternManager(patterns_file=self.patterns_path)
        manager.learn("Radiator 22/500/1200", "K-боковое", "22", 500, 1200)
        
        match = manager.find_match("Radiator 22/500/1200")
        assert match is not None


# ======================================================================
# ТЕСТЫ ДЛЯ CORRESPONDENCE UPDATE (4 теста)
# ======================================================================

class TestCorrespondenceUpdate:
    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.temp_file.close()
        self.patterns_path = self.temp_file.name
    
    def teardown_method(self):
        if os.path.exists(self.patterns_path):
            os.unlink(self.patterns_path)
    
    def test_new_pattern_updates_existing_rows(self):
        manager = PatternManager(patterns_file=self.patterns_path)
        manager.learn("Kermi FTV 11 500/1200", "VK-правое", "22", 600, 1400)
        
        match = manager.find_match("Kermi FTV 11 500/1200")
        assert match is not None
        assert match["rad_type"] == "22"
        assert match["height"] == 600
        assert match["length"] == 1400
    
    def test_multiple_strings_with_same_name(self):
        manager = PatternManager(patterns_file=self.patterns_path)
        
        test_names = [
            "Kermi FTV 11 500/1200",
            "Kermi FTV 11 500/1200 ra",
            "Радиатор Kermi FTV 11 500/1200 RAL 9016",
        ]
        
        manager.learn(test_names[0], "VK-правое", "33", 900, 2000)
        
        for name in test_names:
            match = manager.find_match(name)
            assert match is not None, f"Не найдено: {name}"
            assert match["rad_type"] == "33", f"Для {name} тип должен быть 33"
    
    def test_manual_rows_should_not_be_overwritten(self):
        manager = PatternManager(patterns_file=self.patterns_path)
        manager.learn("Kermi FTV 11 500/1200", "VK-правое", "99", 999, 999)
        
        match = manager.find_match("Совсем другой радиатор 22 600/1400")
        assert match is None


class TestCorrespondenceAfterLearning:
    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.temp_file.close()
        self.patterns_path = self.temp_file.name
    
    def teardown_method(self):
        if os.path.exists(self.patterns_path):
            os.unlink(self.patterns_path)
    
    def test_pattern_is_found_after_saving(self):
        manager1 = PatternManager(patterns_file=self.patterns_path)
        manager1.learn("Kermi FTV 11 500/1200", "VK-правое", "22", 600, 1400)
        manager1.save()
        
        manager2 = PatternManager(patterns_file=self.patterns_path)
        match = manager2.find_match("Kermi FTV 11 500/1200")
        assert match is not None
        assert match["rad_type"] == "22"


# ======================================================================
# ЗАПУСК
# ======================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])