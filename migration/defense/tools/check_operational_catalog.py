"""Validate catalog links and recorded acceptances; percentages count closed scope, not effort."""
import hashlib
import json
from pathlib import Path


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def checked_file(root, reference):
    require(type(reference) is dict and set(reference) == {'path','sha256'}, 'acceptance_reference')
    name, digest = reference['path'], reference['sha256']
    require(isinstance(name,str) and name and not Path(name).is_absolute() and '..' not in Path(name).parts,
            'acceptance_path')
    path = root / name
    require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()) and path.is_file(),'acceptance_path')
    require(path.stat().st_size <= 8*1024*1024,'acceptance_size')
    data = path.read_bytes()
    require(isinstance(digest,str) and hashlib.sha256(data).hexdigest() == digest,'acceptance_digest')
    return data


def completions(value, root, components, disciplines):
    require(type(value) is dict and set(value) == {'schema','acceptances'},'completion_register')
    require(value['schema'] == 'nqc-completion-register-v1' and type(value['acceptances']) is list and len(value['acceptances']) <= 200,
            'completion_register')
    accepted = set()
    for entry in value['acceptances']:
        require(type(entry) is dict and set(entry) == {'id','report'},'completion_entry')
        identifier = entry['id']
        require(isinstance(identifier,str) and identifier in (components.keys() | disciplines.keys()),'completion_id')
        require(identifier not in accepted,'completion_duplicate')
        report = json.loads(checked_file(root,entry['report']))
        require(type(report) is dict and set(report) == {'schema','id','catalog_requirement','full_scope_accepted','checks'},'completion_report')
        expected = components[identifier]['acceptance'] if identifier in components else disciplines[identifier]['competency_check']
        require(report['schema'] == 'nqc-catalog-acceptance-v1' and report['id'] == identifier and
                report['catalog_requirement'] == expected and report['full_scope_accepted'] is True,'completion_scope')
        require(type(report['checks']) is list and 1 <= len(report['checks']) <= 32,'completion_checks')
        for check in report['checks']:
            checked_file(root,check)
        accepted.add(identifier)
    return accepted


def validate(value, root, register=None):
    components = {item['id']: item for item in value['components']}
    disciplines = {item['id']: item for item in value['disciplines']}
    require(len(value['components']) == len(components) == 100,'component_membership')
    require(len(value['disciplines']) == len(disciplines) == 100,'discipline_membership')
    require(set(components) == {f'C{i:03}' for i in range(1,101)},'component_ids')
    require(set(disciplines) == {f'D{i:03}' for i in range(1,101)},'discipline_ids')
    require(len({d['name'] for d in disciplines.values()}) == 100,'discipline_names')
    if register is None:
        register = json.loads((root/'docs/completion_register.json').read_text())
    accepted = completions(register,root,components,disciplines)
    visiting, visited = set(), set()

    def visit(identifier):
        require(identifier not in visiting,'dependency_cycle')
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in components[identifier]['depends_on']:
            require(dependency in components,'unknown_dependency')
            visit(dependency)
        visiting.remove(identifier); visited.add(identifier)

    partial = completed = 0
    for identifier, item in components.items():
        visit(identifier)
        require(identifier == 'C001' or item['depends_on'],'unconnected_root')
        for key in ('name','inputs','outputs','acceptance','technology_candidate','implementation_scope'):
            require(isinstance(item[key],str) and item[key].strip(),'component_description')
        require(item['disciplines'],'component_disciplines')
        for discipline in item['disciplines']:
            require(discipline in disciplines and identifier in disciplines[discipline]['applied_to'],'discipline_link')
        require(item['status'] in ('planned','bounded_partial','complete'),'component_status')
        if item['status'] == 'planned':
            require(item['implementation'] is None,'planned_implementation')
        else:
            path = (root/item['implementation']).resolve()
            require(path.is_relative_to(root.resolve()) and path.is_file(),'implementation_path')
            partial += item['status'] == 'bounded_partial'
            completed += item['status'] == 'complete'
        require((identifier in accepted) == (item['status'] == 'complete'),'completion_status_disagrees')
    for identifier, item in disciplines.items():
        require(item['applied_to'] and item['deliverable'] and item['competency_check'],'discipline_description')
        for component in item['applied_to']:
            require(component in components and identifier in components[component]['disciplines'],'component_link')
    require(value['fully_completed_components'] == completed,'completed_count_disagrees')
    completed_disciplines = len(accepted & disciplines.keys())
    closed = completed + completed_disciplines
    return {'catalog_valid':True,'components':100,'disciplines':100,'bounded_partial_components':partial,
            'planned_components':100-partial-completed,'fully_completed_components':completed,
            'fully_completed_disciplines':completed_disciplines,'dependency_graph_acyclic':True,
            'runtime_integration_of_planned_components_verified':False,
            'progress':{'metric':'recorded_full_scope_acceptances; not effort or time estimate',
                        'total_items':200,'closed_items':closed,'completion_percent':closed*100/200,
                        'not_closed_items':200-closed,'not_closed_percent':(200-closed)*100/200,
                        'component_completion_percent':completed*100/100,
                        'components_with_implementation_percent':(partial+completed)*100/100,
                        'discipline_completion_percent':completed_disciplines*100/100,
                        'disciplines_specified_percent':100.0,
                        'acceptance_records_are_not_independent_certification':True}}


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(validate(json.loads((root/'docs/operational_catalog_100.json').read_text()),root),indent=2))
