# SPDX-License-Identifier: Apache-2.0
"""Read the configuration prefix consumed by ACT's unchanged YAML parser."""
class ConfigHeaderPath:
    def __init__(self,path):self.path=path
    def __getattr__(self,name):return getattr(self.path,name)
    def __str__(self):return str(self.path)
    def read_text(self):
        lines=[]
        with self.path.open() as stream:
            for line in stream:
                lines.append(line)
                if 'END_TEST_CONFIG' in line:break
        return ''.join(lines)

def install():
    import act.parse_test_constraints as constraints
    original=constraints.extract_yaml_config
    count=0
    def parse_header(path):
        nonlocal count
        if count%100==0:print(f'ACT configuration headers: {count}; reading {path.name}',flush=True)
        result=original(ConfigHeaderPath(path))
        count+=1
        return result
    constraints.extract_yaml_config=parse_header
