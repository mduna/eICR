#!/usr/bin/env python3
"""
CDA Element Finder Tool

This tool parses the eICR XPath reference document and finds all matching 
elements in a given CDA XML file. It extracts XPath expressions from the 
reference document and applies them to the provided XML to identify and 
extract relevant data elements.

Usage:
    python cda_element_finder.py <cda_xml_file> [--output output.json] [--format json|csv|text]

Example: python cda_element_finder.py ecr_file.xml --xpath-ref custom_xpath_reference.txt --format text

python cda_element_finder.py ecr_file.xml --xpath-ref custom_xpath_reference.txt --auto-group --show-both --format text --output combined_output.json
"""

import xml.etree.ElementTree as ET
import re
import json
import csv
import sys
import argparse
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path

class XPathParser:
    """Parser for extracting XPath expressions from the reference document."""
    
    def __init__(self):
        self.xpath_patterns = []
    
    def parse_xpath_reference(self, content: str) -> List[Dict[str, str]]:
        """
        Parse the XPath reference content and extract structured information.
        
        Args:
            content: The text content of the XPath reference document
            
        Returns:
            List of dictionaries containing XPath information
        """
        xpath_entries = []
        
        # Split content into lines for processing
        lines = content.split('\n')
        current_entry = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for XPath patterns in the line
            xpath_matches = re.findall(r'[A-Za-z]+[A-Za-z0-9/\[\]@=\'":\.\-_]*(?:/[A-Za-z@\[\]0-9=\'":\.\-_]+)*', line)
            
            # Filter for actual XPath expressions (containing '/' or '@')
            xpath_candidates = [match for match in xpath_matches if ('/' in match or '@' in match) and len(match) > 5]
            
            for xpath in xpath_candidates:
                # Clean up the XPath
                cleaned_xpath = self._clean_xpath(xpath)
                if cleaned_xpath and self._is_valid_xpath(cleaned_xpath):
                    # Try to extract context from surrounding text
                    context = self._extract_context(line, lines)
                    
                    entry = {
                        'xpath': cleaned_xpath,
                        'context': context.get('section', ''),
                        'data_element': context.get('data_element', ''),
                        'template': context.get('template', ''),
                        'cardinality': context.get('cardinality', ''),
                        'business_rules': context.get('business_rules', ''),
                        'original_line': line
                    }
                    xpath_entries.append(entry)
        
        return self._deduplicate_xpaths(xpath_entries)
    
    def _clean_xpath(self, xpath: str) -> str:
        """Clean and normalize XPath expression."""
        # Remove leading/trailing non-xpath characters
        xpath = re.sub(r'^[^A-Za-z/]+', '', xpath)
        xpath = re.sub(r'[^A-Za-z0-9/\[\]@=\'":\.\-_]+$', '', xpath)
        
        # Fix common issues
        xpath = xpath.replace('\\', '')
        
        return xpath.strip()
    
    def _is_valid_xpath(self, xpath: str) -> bool:
        """Basic validation of XPath expression."""
        if len(xpath) < 10:  # Too short to be useful
            return False
        
        # Must contain either a path separator or attribute marker
        if '/' not in xpath and '@' not in xpath:
            return False
            
        # Should start with a reasonable element name or path
        if not re.match(r'^[A-Za-z]', xpath):
            return False
            
        # Common invalid patterns
        invalid_patterns = [
            r'^\d+\.\d+',  # Version numbers
            r'^[A-Z]{1,3}\s',  # Abbreviations
            r'@\w+$',  # Just an attribute
        ]
        
        for pattern in invalid_patterns:
            if re.match(pattern, xpath):
                return False
                
        return True
    
    def _extract_context(self, line: str, all_lines: List[str]) -> Dict[str, str]:
        """Extract context information from the line and surrounding lines."""
        context = {
            'section': '',
            'data_element': '',
            'template': '',
            'cardinality': '',
            'business_rules': ''
        }
        
        # Look for section names, data elements, etc. in the line
        # This is a simplified version - could be enhanced based on document structure
        
        # Extract cardinality patterns like "1..1", "0..*", etc.
        cardinality_match = re.search(r'\b(\d+\.\.\*|\d+\.\.\d+|\d+)\b', line)
        if cardinality_match:
            context['cardinality'] = cardinality_match.group(1)
        
        # Extract template IDs
        template_match = re.search(r'templateId\[@root=[\'"]([^\'"]+)[\'"]', line)
        if template_match:
            context['template'] = template_match.group(1)
        
        return context
    
    def _deduplicate_xpaths(self, entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Remove duplicate XPath entries."""
        seen_xpaths = set()
        unique_entries = []
        
        for entry in entries:
            xpath = entry['xpath']
            if xpath not in seen_xpaths:
                seen_xpaths.add(xpath)
                unique_entries.append(entry)
        
        return unique_entries

class CDAElementFinder:
    """Main class for finding elements in CDA XML using XPath expressions."""
    
    def __init__(self):
        self.namespaces = {
            'cda': 'urn:hl7-org:v3',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'sdtc': 'urn:hl7-org:sdtc',
            'voc': 'http://www.lantanagroup.com/voc'
        }
        self.results = []
    
    def find_elements(self, xml_file: str, xpath_entries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Find all elements in the XML file using the provided XPath expressions.
        
        Args:
            xml_file: Path to the CDA XML file
            xpath_entries: List of XPath entries from the reference document
            
        Returns:
            List of results with found elements
        """
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Register namespaces
            for prefix, uri in self.namespaces.items():
                ET.register_namespace(prefix, uri)
            
            results = []
            
            for entry in xpath_entries:
                xpath = entry['xpath']
                try:
                    # Convert XPath to work with ElementTree
                    converted_xpath = self._convert_xpath_for_et(xpath)
                    
                    # Find elements
                    elements = self._find_elements_by_xpath(root, converted_xpath)
                    
                    if elements:
                        for item in elements:
                            # Handle attribute access results (tuples)
                            if isinstance(item, tuple) and len(item) == 3:
                                element, attr_name, attr_value = item
                                result = {
                                    'original_xpath': xpath,
                                    'converted_xpath': converted_xpath,
                                    'section': entry.get('section', ''),
                                    'data_element': entry.get('data_element', ''),
                                    'template': entry.get('template', ''),
                                    'cardinality': entry.get('cardinality', ''),
                                    'element_tag': element.tag,
                                    'element_text': f"@{attr_name}={attr_value}",
                                    'element_attributes': dict(element.attrib),  # All attributes from element
                                    'element_path': self._get_element_path(element) + f"/@{attr_name}",
                                    'found': True,
                                    'is_attribute': True
                                }
                            else:
                                # Regular element
                                element = item
                                result = {
                                    'original_xpath': xpath,
                                    'converted_xpath': converted_xpath,
                                    'section': entry.get('section', ''),
                                    'data_element': entry.get('data_element', ''),
                                    'template': entry.get('template', ''),
                                    'cardinality': entry.get('cardinality', ''),
                                    'element_tag': element.tag,
                                    'element_text': element.text,
                                    'element_attributes': dict(element.attrib),
                                    'element_path': self._get_element_path(element),
                                    'found': True,
                                    'is_attribute': False
                                }
                            results.append(result)
                    else:
                        # Record that XPath was attempted but no elements found
                        result = {
                            'original_xpath': xpath,
                            'converted_xpath': converted_xpath,
                            'section': entry.get('section', ''),
                            'data_element': entry.get('data_element', ''),
                            'template': entry.get('template', ''),
                            'cardinality': entry.get('cardinality', ''),
                            'element_tag': None,
                            'element_text': None,
                            'element_attributes': {},
                            'element_path': None,
                            'found': False
                        }
                        results.append(result)
                        
                except Exception as e:
                    print(f"Error processing XPath '{xpath}': {str(e)}")
                    continue
            
            return results
            
        except ET.ParseError as e:
            raise Exception(f"Error parsing XML file: {str(e)}")
        except FileNotFoundError:
            raise Exception(f"XML file not found: {xml_file}")
    
    def _convert_xpath_for_et(self, xpath: str) -> str:
        """
        Convert XPath expression to work with ElementTree.
        ElementTree has limited XPath support, so we need to simplify.
        """
        # Store original for reference
        original_xpath = xpath
        
        # Add namespace prefixes where needed
        converted = xpath
        
        # Replace common CDA elements with namespaced versions
        cda_elements = [
            'ClinicalDocument', 'recordTarget', 'patientRole', 'patient',
            'encompassingEncounter', 'observation', 'organizer', 'entry',
            'section', 'component', 'act', 'substanceAdministration', 'name',
            'given', 'family', 'addr', 'city', 'state', 'telecom', 'effectiveTime',
            'title', 'id', 'administrativeGenderCode', 'birthTime', 'raceCode',
            'low', 'high', 'methodCode', 'author', 'time', 'value', 'templateId',
            'country', 'postalCode', 'county', 'streetAddressLine', 'componentOf',
            'location', 'healthCareFacility', 'serviceProviderOrganization', 'statusCode',
            'code', 'displayName', 'codeSystemName', 'procedure', 'participant', 'participantRole'
        ]
        
        # Handle special case: any element with templateId predicate
        templateid_match = re.search(r'(\w+)\[templateId\[@root=[\'"]([^\'"]+)[\'"]\]\]', converted)
        if templateid_match:
            # Store the templateId for later use
            element_type = templateid_match.group(1)
            self._current_templateid = templateid_match.group(2)
            self._current_element_type = element_type
            # Replace with simple element for ElementTree
            converted = re.sub(r'\w+\[templateId\[@root=[\'"][^\'"]+[\'"]\]\]', element_type, converted)
        else:
            self._current_templateid = None
            self._current_element_type = None
        
        # Split path and process each element
        path_parts = converted.split('/')
        processed_parts = []
        
        for i, part in enumerate(path_parts):
            if not part:  # Handle leading slash
                processed_parts.append('')
                continue
                
            # Special handling for ClinicalDocument at the start
            if i == 0 and part == 'ClinicalDocument':
                # Skip ClinicalDocument since we're already at the root
                continue
            elif i == 1 and path_parts[0] == 'ClinicalDocument':
                # First element after ClinicalDocument should be relative
                if '@' in part:
                    processed_parts.append(part)
                elif '[' in part:
                    element_name = part.split('[')[0]
                    predicate = part[len(element_name):]
                    if element_name in cda_elements:
                        processed_parts.append(f'./cda:{element_name}{predicate}')
                    else:
                        processed_parts.append(f'./{part}')
                else:
                    if part in cda_elements:
                        processed_parts.append(f'./cda:{part}')
                    else:
                        processed_parts.append(f'./{part}')
                continue
                
            # Extract element name and any attributes/predicates
            if '@' in part:
                # This is an attribute access
                processed_parts.append(part)
            elif '[' in part:
                # This has predicates - handle carefully
                element_name = part.split('[')[0]
                predicate = part[len(element_name):]
                if element_name in cda_elements and not element_name.startswith('cda:'):
                    processed_parts.append(f'cda:{element_name}{predicate}')
                else:
                    processed_parts.append(part)
            else:
                # Simple element name
                if part in cda_elements and not part.startswith('cda:'):
                    processed_parts.append(f'cda:{part}')
                else:
                    processed_parts.append(part)
        
        converted = '/'.join(processed_parts)
        
        # Handle cases where we end up with just an attribute
        if converted.startswith('/@'):
            converted = '.' + converted
        
        # For xpath starting with any CDA element (not under ClinicalDocument), make it search everywhere
        cda_search_elements = ['observation', 'act', 'organizer', 'substanceAdministration', 'encounter', 'procedure']
        if any(converted.startswith(elem) or converted.startswith(f'cda:{elem}') for elem in cda_search_elements):
            converted = './/' + converted
        
        # Simplify other complex predicates that ET can't handle (but not templateId - we handled that above)
        converted = re.sub(r'\[contains\([^)]+\)\]', '', converted)
        
        return converted
    
    def _find_elements_by_xpath(self, root: ET.Element, xpath: str) -> List[ET.Element]:
        """
        Find elements using XPath with fallback methods for ElementTree limitations.
        """
        try:
            # Try direct XPath first
            elements = root.findall(xpath, self.namespaces)
            if elements:
                return elements
        except:
            pass
        
        # Check if this is a templateId predicate XPath that was simplified
        if self._has_templateid_predicate(xpath):
            return self._find_elements_with_templateid(root, xpath)
            
        # If XPath failed or found nothing, try attribute access
        if xpath.endswith('/@value') or '@' in xpath:
            # Handle attribute access specially
            return self._find_elements_with_attributes(root, xpath)
        
        # Fallback: try to find elements by breaking down the path
        return self._find_elements_recursive(root, xpath)
    
    def _has_templateid_predicate(self, xpath: str) -> bool:
        """Check if the original XPath had a templateId predicate that was stripped."""
        # Check if we have a stored templateId from the conversion process
        return hasattr(self, '_current_templateid') and self._current_templateid is not None
    
    def _find_elements_with_templateid(self, root: ET.Element, xpath: str) -> List[ET.Element]:
        """Handle XPath expressions that originally had templateId predicates."""
        # Use the stored templateId from the conversion process
        target_templateid = getattr(self, '_current_templateid', None)
        element_type = getattr(self, '_current_element_type', None)
        
        # If no templateId was captured, try to extract it from the original XPath
        if not target_templateid or not element_type:
            # This is a fallback - shouldn't normally happen with the improved conversion
            return []
        
        # Find all elements of the specified type
        all_elements = root.findall(f'.//cda:{element_type}', self.namespaces)
        
        # Filter by templateId
        matching_elements = []
        for elem in all_elements:
            template_ids = elem.findall('./cda:templateId', self.namespaces)
            for template in template_ids:
                if template.attrib.get('root') == target_templateid:
                    matching_elements.append(elem)
                    break
        
        # If the xpath continues after the element, navigate further
        if '/code' in xpath:
            result_elements = []
            for elem in matching_elements:
                if xpath.endswith('/@code'):
                    # Looking for code attribute
                    code_elem = elem.find('./cda:code', self.namespaces)
                    if code_elem is not None and 'code' in code_elem.attrib:
                        result_elements.append((code_elem, 'code', code_elem.attrib['code']))
                elif xpath.endswith('/code'):
                    # Looking for code element
                    code_elem = elem.find('./cda:code', self.namespaces)
                    if code_elem is not None:
                        result_elements.append(code_elem)
            return result_elements
        
        elif '/value' in xpath:
            result_elements = []
            for elem in matching_elements:
                if xpath.endswith('/@value'):
                    # Looking for value attribute
                    value_elem = elem.find('./cda:value', self.namespaces)
                    if value_elem is not None and 'value' in value_elem.attrib:
                        # Check if this value element belongs to a nested template
                        if not self._is_from_nested_template(value_elem, elem, target_templateid):
                            result_elements.append((value_elem, 'value', value_elem.attrib['value']))
                elif xpath.endswith('/@code'):
                    # Looking for code attribute on value element
                    value_elem = elem.find('./cda:value', self.namespaces)
                    if value_elem is not None and 'code' in value_elem.attrib:
                        # Check if this value element belongs to a nested template
                        if not self._is_from_nested_template(value_elem, elem, target_templateid):
                            result_elements.append((value_elem, 'code', value_elem.attrib['code']))
                elif xpath.endswith('/value'):
                    # Looking for value element
                    value_elem = elem.find('./cda:value', self.namespaces)
                    if value_elem is not None:
                        # Check if this value element belongs to a nested template
                        if not self._is_from_nested_template(value_elem, elem, target_templateid):
                            result_elements.append(value_elem)
            return result_elements
        
        elif '/text' in xpath:
            result_elements = []
            for elem in matching_elements:
                text_elem = elem.find('./cda:text', self.namespaces)
                if text_elem is not None:
                    result_elements.append(text_elem)
            return result_elements
        
        elif '/statusCode' in xpath:
            result_elements = []
            for elem in matching_elements:
                if xpath.endswith('/@code'):
                    status_elem = elem.find('./cda:statusCode', self.namespaces)
                    if status_elem is not None and 'code' in status_elem.attrib:
                        result_elements.append((status_elem, 'code', status_elem.attrib['code']))
                else:
                    status_elem = elem.find('./cda:statusCode', self.namespaces)
                    if status_elem is not None:
                        result_elements.append(status_elem)
            return result_elements
        
        elif '/methodCode' in xpath or '/cda:methodCode' in xpath:
            result_elements = []
            for elem in matching_elements:
                if xpath.endswith('/@code'):
                    method_elem = elem.find('./cda:methodCode', self.namespaces)
                    if method_elem is not None and 'code' in method_elem.attrib:
                        result_elements.append((method_elem, 'code', method_elem.attrib['code']))
                else:
                    method_elem = elem.find('./cda:methodCode', self.namespaces)
                    if method_elem is not None:
                        result_elements.append(method_elem)
            return result_elements
        
        elif '/effectiveTime/low' in xpath or '/cda:effectiveTime/cda:low' in xpath:
            result_elements = []
            for elem in matching_elements:
                if xpath.endswith('/@value'):
                    effective_time = elem.find('./cda:effectiveTime', self.namespaces)
                    if effective_time is not None:
                        low_elem = effective_time.find('./cda:low', self.namespaces)
                        if low_elem is not None and 'value' in low_elem.attrib:
                            result_elements.append((low_elem, 'value', low_elem.attrib['value']))
                else:
                    effective_time = elem.find('./cda:effectiveTime', self.namespaces)
                    if effective_time is not None:
                        low_elem = effective_time.find('./cda:low', self.namespaces)
                        if low_elem is not None:
                            result_elements.append(low_elem)
            return result_elements
        
        elif '/author/time' in xpath or '/cda:author/cda:time' in xpath:
            result_elements = []
            for elem in matching_elements:
                if xpath.endswith('/@value'):
                    author_elem = elem.find('./cda:author', self.namespaces)
                    if author_elem is not None:
                        time_elem = author_elem.find('./cda:time', self.namespaces)
                        if time_elem is not None and 'value' in time_elem.attrib:
                            result_elements.append((time_elem, 'value', time_elem.attrib['value']))
                else:
                    author_elem = elem.find('./cda:author', self.namespaces)
                    if author_elem is not None:
                        time_elem = author_elem.find('./cda:time', self.namespaces)
                        if time_elem is not None:
                            result_elements.append(time_elem)
            return result_elements
        
        # Return the matching elements themselves if no sub-path specified
        return matching_elements
    
    def _find_elements_with_attributes(self, root: ET.Element, xpath: str) -> List[ET.Element]:
        """Handle XPath expressions that access attributes."""
        # Split the XPath into element path and attribute
        if '/@' in xpath:
            element_path, attr_name = xpath.rsplit('/@', 1)
        else:
            return []
        
        # Find the elements first
        try:
            elements = root.findall(element_path, self.namespaces)
        except:
            elements = self._find_elements_recursive(root, element_path)
        
        # Filter elements that have the requested attribute and return tuples
        result_elements = []
        for elem in elements:
            if attr_name in elem.attrib:
                # Return a tuple of (element, attribute_name, attribute_value)
                result_elements.append((elem, attr_name, elem.attrib[attr_name]))
        
        return result_elements
    
    def _find_elements_recursive(self, root: ET.Element, xpath: str) -> List[ET.Element]:
        """
        Recursive fallback method for finding elements when XPath fails.
        """
        # This is a simplified fallback - could be enhanced for more complex XPaths
        parts = xpath.split('/')
        current_elements = [root]
        
        for part in parts:
            if not part:
                continue
                
            next_elements = []
            for elem in current_elements:
                # Remove namespace prefix for searching
                clean_part = part.split(':')[-1] if ':' in part else part
                clean_part = clean_part.split('[')[0]  # Remove predicates
                
                # Find child elements matching this part
                for child in elem:
                    if child.tag.endswith(clean_part) or clean_part in child.tag:
                        next_elements.append(child)
            
            current_elements = next_elements
            if not current_elements:
                break
        
        return current_elements
    
    def _get_element_path(self, element: ET.Element) -> str:
        """Get the path to an element in the XML tree."""
        path_parts = []
        current = element
        
        while current is not None:
            tag = current.tag
            if '}' in tag:
                tag = tag.split('}')[1]  # Remove namespace
            path_parts.insert(0, tag)
            current = current.getparent() if hasattr(current, 'getparent') else None
        
        return '/' + '/'.join(path_parts)
    
    def find_elements_with_auto_grouping(self, xml_file: str, xpath_entries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Find elements and automatically group them by templateId.
        
        Args:
            xml_file: Path to the CDA XML file
            xpath_entries: List of XPath entries from the reference document
            
        Returns:
            List of grouped results organized by templateId
        """
        # First find all individual elements
        individual_results = self.find_elements(xml_file, xpath_entries)
        
        # Group the XPath entries by templateId automatically
        grouped_entries = self.auto_group_xpath_entries(xpath_entries)
        
        # Process each group
        grouped_results = []
        
        for template_id, group_xpaths in grouped_entries.items():
            group_result = self.find_grouped_elements(xml_file, group_xpaths, template_id)
            if group_result['instances']:  # Only include groups with found instances
                grouped_results.append(group_result)
        
        return grouped_results
    
    def auto_group_xpath_entries(self, xpath_entries: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
        """
        Automatically group XPath entries by extracting templateId from XPath expressions.
        
        Args:
            xpath_entries: List of XPath entries
            
        Returns:
            Dictionary mapping templateId to list of related XPath entries
        """
        groups = {}
        ungrouped = []
        
        for entry in xpath_entries:
            xpath = entry['xpath']
            
            # Extract templateId from XPath expression
            template_match = re.search(r'templateId\[@root=[\'"]([^\'"]+)[\'"]', xpath)
            
            if template_match:
                template_id = template_match.group(1)
                
                if template_id not in groups:
                    groups[template_id] = []
                
                # Add enhanced information including xpath_expressions
                enhanced_entry = entry.copy()
                enhanced_entry['xpath_expressions'] = [xpath]
                groups[template_id].append(enhanced_entry)
            else:
                ungrouped.append(entry)
        
        # Add ungrouped items as a separate category if they exist
        if ungrouped:
            groups['ungrouped'] = ungrouped
            
        return groups
    
    def find_grouped_elements(self, xml_file: str, xpath_entries: List[Dict[str, str]], template_id: str = None) -> Dict[str, Any]:
        """
        Find elements for a specific template group and organize them by instances.
        
        Args:
            xml_file: Path to the CDA XML file
            xpath_entries: List of XPath entries for this template
            template_id: The templateId for this group
            
        Returns:
            Grouped results with instances
        """
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Register namespaces
            for prefix, uri in self.namespaces.items():
                ET.register_namespace(prefix, uri)
            
            # Find all elements of the template type first
            if template_id and template_id != 'ungrouped':
                # Find all elements with this templateId
                template_elements = self._find_template_instances(root, template_id)
            else:
                # For ungrouped items, we'll process them individually
                template_elements = []
            
            instances = []
            
            if template_elements:
                # Process each template instance
                for i, template_elem in enumerate(template_elements):
                    instance_data = {
                        'instance_number': i + 1,
                        'template_id': template_id,
                        'fields': {},
                        'xpath_expressions': []  # Track which XPaths were used
                    }
                    
                    # Apply each XPath within this template instance
                    for entry in xpath_entries:
                        xpath = entry['xpath']
                        
                        # Get the relative XPath (part after the templateId predicate)
                        relative_xpath = self._get_relative_xpath(xpath)
                        instance_data['xpath_expressions'].append(xpath)
                        
                        try:
                            field_results = self._find_within_template_instance(template_elem, relative_xpath, xpath)
                            
                            if field_results:
                                field_name = self._extract_field_name(xpath)
                                instance_data['fields'][field_name] = field_results
                                
                        except Exception as e:
                            print(f"Error processing XPath '{xpath}' in template instance: {str(e)}")
                            continue
                    
                    # Only add instance if it has some data
                    if instance_data['fields']:
                        instances.append(instance_data)
            
            # Determine template description
            template_descriptions = {
                '2.16.840.1.113883.10.20.22.4.2': 'Problem Observation',
                '2.16.840.1.113883.10.20.22.4.27': 'Vital Signs Observation', 
                '2.16.840.1.113883.10.20.22.4.7': 'Allergy Observation',
                '2.16.840.1.113883.10.20.22.4.13': 'Medication Activity',
                '2.16.840.1.113883.10.20.22.4.44': 'Lab Result Observation',
                '2.16.840.1.113883.10.20.22.4.14': 'Medication Supply Order',
                '2.16.840.1.113883.10.20.22.4.16': 'Medication Dispense',
                '2.16.840.1.113883.10.20.22.4.19': 'Medication Order',
                '2.16.840.1.113883.10.20.22.4.49': 'Pregnancy Observation',
                '2.16.840.1.113883.10.20.22.4.78': 'Smoking Status Observation',
                '2.16.840.1.113883.10.20.22.4.280': 'Gestational Age Observation'
            }
            
            template_description = template_descriptions.get(template_id, f'Template {template_id}' if template_id else 'Ungrouped')
            
            return {
                'template_id': template_id,
                'template_description': template_description,
                'xpath_expressions': [entry['xpath'] for entry in xpath_entries],  # Include source XPaths
                'instance_count': len(instances),
                'instances': instances
            }
            
        except ET.ParseError as e:
            raise Exception(f"Error parsing XML file: {str(e)}")
        except FileNotFoundError:
            raise Exception(f"XML file not found: {xml_file}")
    
    def _find_template_instances(self, root: ET.Element, template_id: str) -> List[ET.Element]:
        """Find all instances of elements with the specified templateId."""
        instances = []
        
        # Search for any element with the given templateId
        for elem in root.iter():
            template_ids = elem.findall('./cda:templateId', self.namespaces)
            for template in template_ids:
                if template.attrib.get('root') == template_id:
                    instances.append(elem)
                    break
        
        return instances
    
    def _get_relative_xpath(self, xpath: str) -> str:
        """Extract the part of XPath after the templateId predicate."""
        # Look for the pattern: element[templateId[@root='...']]
        match = re.search(r'\w+\[templateId\[@root=[\'"][^\'"]+[\'"]\]\](.*)$', xpath)
        if match:
            relative_part = match.group(1)
            # Remove leading slash if present
            return relative_part.lstrip('/')
        else:
            # If no templateId predicate, return the whole xpath
            return xpath
    
    def _find_within_template_instance(self, template_elem: ET.Element, relative_xpath: str, full_xpath: str) -> List[Dict[str, Any]]:
        """Find elements within a specific template instance, excluding nested templates."""
        if not relative_xpath:
            # This is the template element itself
            return [{
                'text': template_elem.text,
                'attributes': dict(template_elem.attrib),
                'tag': template_elem.tag
            }]
        
        results = []
        
        try:
            # Check if the XPath contains templateId predicates that ElementTree can't handle
            if 'templateId[@root=' in relative_xpath:
                # Handle complex templateId predicates manually
                results = self._handle_complex_xpath_with_templateid(template_elem, relative_xpath)
            else:
                # Convert relative XPath for ElementTree
                converted_xpath = self._convert_relative_xpath(relative_xpath)
                
                # Handle attribute access
                if '/@' in converted_xpath:
                    element_path, attr_name = converted_xpath.rsplit('/@', 1)
                    if element_path:
                        elements = template_elem.findall(element_path, self.namespaces)
                    else:
                        elements = [template_elem]  # Attribute on template element itself
                    
                    for elem in elements:
                        # Skip elements that belong to nested templates
                        if self._is_nested_template_element(elem, template_elem):
                            continue
                            
                        if attr_name in elem.attrib:
                            results.append({
                                'text': f"@{attr_name}={elem.attrib[attr_name]}",
                                'attributes': {attr_name: elem.attrib[attr_name]},
                                'tag': elem.tag,
                                'attribute_name': attr_name,
                                'attribute_value': elem.attrib[attr_name]
                            })
                else:
                    # Regular element search
                    elements = template_elem.findall(converted_xpath, self.namespaces)
                    for elem in elements:
                        # Skip elements that belong to nested templates
                        if self._is_nested_template_element(elem, template_elem):
                            continue
                            
                        results.append({
                            'text': elem.text,
                            'attributes': dict(elem.attrib),
                            'tag': elem.tag
                        })
        
        except Exception as e:
            print(f"Error in _find_within_template_instance for XPath '{relative_xpath}': {str(e)}")
        
        return results
    
    def _handle_complex_xpath_with_templateid(self, template_elem: ET.Element, xpath: str) -> List[Dict[str, Any]]:
        """Handle XPaths that contain templateId predicates which ElementTree can't process."""
        import re
        
        results = []
        
        # Parse the XPath to extract parts and templateId requirements
        # Example: participant[templateId[@root='2.16.840.1.113883.10.20.22.4.410']]/participantRole/id/@root
        
        # Split by parts with templateId predicates
        parts = xpath.split('/')
        current_elements = [template_elem]
        
        for part in parts:
            if not part:
                continue
                
            next_elements = []
            
            # Check if this part has a templateId predicate
            templateid_match = re.search(r'(\w+)\[templateId\[@root=[\'"]([^\'"]+)[\'"]\]\]', part)
            
            if templateid_match:
                element_name = templateid_match.group(1)
                required_templateid = templateid_match.group(2)
                
                # Find all elements of this type
                for current_elem in current_elements:
                    candidates = current_elem.findall(f'.//cda:{element_name}', self.namespaces)
                    
                    # Filter by templateId
                    for candidate in candidates:
                        # Skip elements that belong to nested templates (but be more careful about this)
                        if candidate != template_elem and self._has_different_template_ancestor(candidate, template_elem):
                            continue
                            
                        template_ids = candidate.findall('cda:templateId', self.namespaces)
                        for tid in template_ids:
                            if tid.get('root') == required_templateid:
                                next_elements.append(candidate)
                                break
            
            elif part.startswith('@'):
                # Handle attribute access
                attr_name = part[1:]  # Remove @
                for current_elem in current_elements:
                    if attr_name in current_elem.attrib:
                        results.append({
                            'text': f"@{attr_name}={current_elem.attrib[attr_name]}",
                            'attributes': {attr_name: current_elem.attrib[attr_name]},
                            'tag': current_elem.tag,
                            'attribute_name': attr_name,
                            'attribute_value': current_elem.attrib[attr_name]
                        })
                return results  # Attributes are terminal
            
            else:
                # Regular element without templateId predicate
                for current_elem in current_elements:
                    candidates = current_elem.findall(f'.//cda:{part}', self.namespaces)
                    for candidate in candidates:
                        # Skip elements that belong to nested templates (but be more careful about this)
                        if candidate != template_elem and self._has_different_template_ancestor(candidate, template_elem):
                            continue
                        next_elements.append(candidate)
            
            current_elements = next_elements
            if not current_elements:
                break
        
        # If we end with elements (not attributes), add them to results
        for elem in current_elements:
            results.append({
                'text': elem.text,
                'attributes': dict(elem.attrib),
                'tag': elem.tag
            })
        
        return results
    
    def _has_different_template_ancestor(self, element: ET.Element, template_root: ET.Element) -> bool:
        """Check if an element has a different template ancestor than the template_root."""
        # For now, let's be less strict and only exclude if we find a clear nested template
        # This is a simplified check - you might want to make it more sophisticated
        current = element
        while current is not None and current != template_root:
            # Check if this element has templateId that would make it a different template
            template_ids = current.findall('cda:templateId', self.namespaces)
            for tid in template_ids:
                # If we find a templateId that's different from our template_root's templateId
                root_template_ids = template_root.findall('cda:templateId', self.namespaces)
                root_template_id = root_template_ids[0].get('root') if root_template_ids else None
                if tid.get('root') != root_template_id and current != element:  # Don't exclude the element itself
                    return True
            current = current.getparent() if hasattr(current, 'getparent') else None
        return False
    
    def _is_nested_template_element(self, element: ET.Element, template_root: ET.Element) -> bool:
        """Check if an element belongs to a nested template within the current template."""
        # Alternative approach: check if the element belongs to a different template instance
        # by walking up to find the immediate template container
        
        # Find all template instances that are descendants of template_root
        nested_templates = []
        for descendant in template_root.iter():
            if descendant != template_root:  # Don't include the root template itself
                template_ids = descendant.findall('./cda:templateId', self.namespaces)
                if template_ids:
                    nested_templates.append(descendant)
        
        # Check if the element is contained within any of these nested templates
        for nested_template in nested_templates:
            # Check if element is within this nested template
            for nested_elem in nested_template.iter():
                if nested_elem == element:
                    return True
        
        return False
    
    def _is_from_nested_template(self, element: ET.Element, template_root: ET.Element, target_template_id: str) -> bool:
        """Check if an element belongs to a nested template different from the target template."""
        # Walk up from the element to see if there's another templateId between
        # this element and the template_root that's different from our target
        current = element
        
        while current is not None and current != template_root:
            parent = current.getparent() if hasattr(current, 'getparent') else None
            if parent is None:
                break
                
            # Check if the parent has templateId children
            if parent != template_root:
                template_ids = parent.findall('./cda:templateId', self.namespaces)
                for template_id_elem in template_ids:
                    template_id = template_id_elem.attrib.get('root')
                    if template_id and template_id != target_template_id:
                        # This element is inside a different nested template
                        return True
                        
            current = parent
            
        return False
    
    def _convert_relative_xpath(self, xpath: str) -> str:
        """Convert relative XPath for use within a template instance."""
        if not xpath:
            return '.'
        
        # Add CDA namespace prefix where needed
        cda_elements = [
            'code', 'value', 'text', 'statusCode', 'methodCode', 'effectiveTime', 
            'low', 'high', 'author', 'time', 'entryRelationship', 'observation',
            'organizer', 'component', 'section', 'entry', 'act', 'substanceAdministration',
            'participant', 'participantRole', 'id', 'templateId', 'procedure'
        ]
        
        # Split path and add namespace prefixes
        parts = xpath.split('/')
        converted_parts = []
        
        for part in parts:
            if not part:
                continue
            
            # Handle attributes
            if part.startswith('@'):
                converted_parts.append(part)
                continue
            
            # Extract element name (before any predicates)
            element_name = part.split('[')[0]
            predicate = part[len(element_name):] if '[' in part else ''
            
            # Add namespace if needed
            if element_name in cda_elements and not element_name.startswith('cda:'):
                converted_parts.append(f'cda:{element_name}{predicate}')
            else:
                converted_parts.append(part)
        
        result = './/' + '/'.join(converted_parts) if converted_parts else '.'
        
        # Handle direct child access (single ./)
        if not xpath.startswith('.') and len(converted_parts) == 1:
            result = './' + '/'.join(converted_parts)
        
        return result
    
    def _extract_field_name(self, xpath: str) -> str:
        """Extract a readable field name from XPath expression."""
        # Try to extract meaningful field name from XPath
        
        # Handle attribute access
        if '/@' in xpath:
            attr_name = xpath.split('/@')[-1]
            element_part = xpath.split('/@')[0]
            
            # Get the last few elements before the attribute for better context
            if '/' in element_part:
                path_parts = element_part.split('/')
                # Take the last 2-3 meaningful parts for context
                meaningful_parts = []
                for part in reversed(path_parts):
                    if part and not part.startswith('templateId'):
                        # Remove namespace prefixes and predicates
                        clean_part = part.split('[')[0].split(':')[-1]
                        if clean_part not in ['observation', 'organizer', 'act']:  # Skip generic element types
                            meaningful_parts.insert(0, clean_part)
                        if len(meaningful_parts) >= 2:  # Limit to 2 parts for readability
                            break
                
                if meaningful_parts:
                    return f"{'/'.join(meaningful_parts)}/{attr_name}"
                else:
                    # Fallback: use last element
                    last_element = path_parts[-1].split('[')[0].split(':')[-1]
                    return f"{last_element}_{attr_name}"
            else:
                return attr_name
        
        # For regular elements, get the last meaningful part of the path
        parts = xpath.split('/')
        if parts:
            # Take last 2 meaningful parts
            meaningful_parts = []
            for part in reversed(parts):
                if part and not part.startswith('templateId'):
                    clean_part = part.split('[')[0].split(':')[-1]
                    if clean_part not in ['observation', 'organizer', 'act']:
                        meaningful_parts.insert(0, clean_part)
                    if len(meaningful_parts) >= 2:
                        break
            
            if meaningful_parts:
                return '/'.join(meaningful_parts)
            else:
                # Fallback
                last_part = parts[-1]
                field_name = last_part.split('[')[0].split(':')[-1]
                return field_name
        
        return "unknown_field"
    
    def demonstrate_grouped_problem_observations(self, xml_file: str):
        """
        Demonstrate the grouped functionality with problem observations.
        
        Args:
            xml_file: Path to the CDA XML file
        """
        print("=== Grouped Problem Observations Demonstration ===")
        
        # Define problem observation XPaths
        problem_xpaths = [
            {
                'xpath': "observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/code/@code",
                'context': 'Problem Observation',
                'data_element': 'Problem Code',
                'template': '2.16.840.1.113883.10.20.22.4.2'
            },
            {
                'xpath': "observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/code/@displayName", 
                'context': 'Problem Observation',
                'data_element': 'Problem Display Name',
                'template': '2.16.840.1.113883.10.20.22.4.2'
            },
            {
                'xpath': "observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/value/@code",
                'context': 'Problem Observation', 
                'data_element': 'Problem Value Code',
                'template': '2.16.840.1.113883.10.20.22.4.2'
            },
            {
                'xpath': "observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/value/@displayName",
                'context': 'Problem Observation',
                'data_element': 'Problem Value Display Name', 
                'template': '2.16.840.1.113883.10.20.22.4.2'
            },
            {
                'xpath': "observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/statusCode/@code",
                'context': 'Problem Observation',
                'data_element': 'Status Code',
                'template': '2.16.840.1.113883.10.20.22.4.2'
            },
            {
                'xpath': "observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/effectiveTime/low/@value",
                'context': 'Problem Observation',
                'data_element': 'Effective Time Low',
                'template': '2.16.840.1.113883.10.20.22.4.2'
            }
        ]
        
        try:
            # Find grouped elements
            grouped_result = self.find_grouped_elements(xml_file, problem_xpaths, '2.16.840.1.113883.10.20.22.4.2')
            
            print(f"Template: {grouped_result['template_description']}")
            print(f"Template ID: {grouped_result['template_id']}")
            print(f"Found {grouped_result['instance_count']} instances")
            print("")
            
            # Display each instance
            for instance in grouped_result['instances']:
                print(f"Instance {instance['instance_number']}:")
                for field_name, field_data in instance['fields'].items():
                    print(f"  {field_name}:")
                    for item in field_data:
                        if 'attribute_value' in item:
                            print(f"    {item['attribute_name']}: {item['attribute_value']}")
                        else:
                            print(f"    Text: {item['text']}")
                            if item['attributes']:
                                print(f"    Attributes: {item['attributes']}")
                print("")
            
        except Exception as e:
            print(f"Error in demonstration: {str(e)}")

class OutputFormatter:
    """Handles different output formats for the results."""
    
    @staticmethod
    def format_json(results: List[Dict[str, Any]], output_file: str = None) -> str:
        """Format results as JSON."""
        json_output = json.dumps(results, indent=2, ensure_ascii=False)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_output)
        
        return json_output
    
    @staticmethod
    def format_csv(results: List[Dict[str, Any]], output_file: str = None) -> str:
        """Format results as CSV."""
        if not results:
            return ""
        
        # Get all unique keys from results
        all_keys = set()
        for result in results:
            all_keys.update(result.keys())
        
        fieldnames = sorted(list(all_keys))
        
        if output_file:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for result in results:
                    # Convert complex objects to strings
                    row = {}
                    for key in fieldnames:
                        value = result.get(key, '')
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value)
                        row[key] = value
                    writer.writerow(row)
        
        return f"CSV output written to {output_file}" if output_file else ""
    
    @staticmethod
    def format_text(results: List[Dict[str, Any]], output_file: str = None) -> str:
        """Format results as human-readable text."""
        text_output = []
        
        # Group results by found/not found
        found_results = [r for r in results if r.get('found', False)]
        not_found_results = [r for r in results if not r.get('found', False)]
        
        text_output.append(f"CDA Element Analysis Results")
        text_output.append(f"=" * 50)
        text_output.append(f"Total XPaths processed: {len(results)}")
        text_output.append(f"Elements found: {len(found_results)}")
        text_output.append(f"Elements not found: {len(not_found_results)}")
        text_output.append("")
        
        if found_results:
            text_output.append("FOUND ELEMENTS:")
            text_output.append("-" * 30)
            
            for result in found_results:
                text_output.append(f"XPath: {result['original_xpath']}")
                text_output.append(f"  Element: {result['element_tag']}")
                text_output.append(f"  Text: {result['element_text']}")
                
                # Enhanced attribute display with displayName highlighted
                attrs = result['element_attributes']
                if attrs:
                    if 'displayName' in attrs:
                        text_output.append(f"  DisplayName: {attrs['displayName']}")
                    if 'code' in attrs:
                        text_output.append(f"  Code: {attrs['code']}")
                    if 'value' in attrs:
                        text_output.append(f"  Value: {attrs['value']}")
                    
                    # Show all other attributes
                    other_attrs = {k: v for k, v in attrs.items() if k not in ['displayName', 'code', 'value']}
                    if other_attrs:
                        text_output.append(f"  Other Attributes: {other_attrs}")
                else:
                    text_output.append(f"  Attributes: {attrs}")
                
                ##text_output.append(f"  Section: {result['section']}")
                text_output.append("")
        
        if not_found_results:
            text_output.append("NOT FOUND ELEMENTS:")
            text_output.append("-" * 30)
            
            for result in not_found_results[:10]:  # Limit to first 10
                text_output.append(f"XPath: {result['original_xpath']}")
                ##text_output.append(f"  Section: {result['section']}")
                text_output.append("")
        
        formatted_text = '\n'.join(text_output)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(formatted_text)
        
        return formatted_text
    
    @staticmethod
    def format_grouped_json(results: List[Dict[str, Any]], output_file: str = None) -> str:
        """Format grouped results as JSON."""
        json_output = json.dumps(results, indent=2, ensure_ascii=False)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_output)
        
        return json_output
    
    @staticmethod
    def format_grouped_text(results: List[Dict[str, Any]], output_file: str = None) -> str:
        """Format grouped results as human-readable text."""
        text_output = []
        
        text_output.append("CDA Grouped Element Analysis Results")
        text_output.append("=" * 50)
        
        total_instances = sum(len(group['instances']) for group in results)
        text_output.append(f"Total template groups: {len(results)}")
        text_output.append(f"Total instances found: {total_instances}")
        text_output.append("")
        
        for group in results:
            text_output.append(f"Template: {group['template_description']}")
            text_output.append(f"Template ID: {group['template_id']}")
            text_output.append(f"Instances: {group['instance_count']}")
            
            # Show the XPath expressions used for this group
            if 'xpath_expressions' in group and group['xpath_expressions']:
                text_output.append("XPath Expressions:")
                for xpath in group['xpath_expressions']:
                    text_output.append(f"  - {xpath}")
            
            text_output.append("-" * 40)
            
            # Display each instance
            for instance in group['instances']:
                text_output.append(f"Instance {instance['instance_number']}:")
                
                # Group related fields together (code, displayName, codeSystemName)
                grouped_fields = OutputFormatter._group_related_fields(instance['fields'])
                
                for base_field, related_data in grouped_fields.items():
                    text_output.append(f"  {base_field}:")
                    for item in related_data:
                        if 'attribute_value' in item:
                            # Format combined attributes on one line
                            line_parts = []
                            line_parts.append(f"Code: {item.get('attribute_value', '')}")
                            
                            # Look for corresponding displayName and codeSystemName
                            if 'related_displayName' in item:
                                line_parts.append(f"DisplayName: {item['related_displayName']}")
                            if 'related_codeSystemName' in item:
                                line_parts.append(f"System: {item['related_codeSystemName']}")
                            
                            text_output.append(f"    {' | '.join(line_parts)}")
                        else:
                            if item.get('text'):
                                text_output.append(f"    Text: {item['text']}")
                            if item.get('attributes'):
                                # Enhanced attribute display with displayName highlighted
                                attrs = item['attributes']
                                line_parts = []
                                if 'code' in attrs:
                                    line_parts.append(f"Code: {attrs['code']}")
                                if 'displayName' in attrs:
                                    line_parts.append(f"DisplayName: {attrs['displayName']}")
                                if 'codeSystemName' in attrs:
                                    line_parts.append(f"System: {attrs['codeSystemName']}")
                                if 'value' in attrs:
                                    line_parts.append(f"Value: {attrs['value']}")
                                
                                if line_parts:
                                    text_output.append(f"    {' | '.join(line_parts)}")
                                
                                # Show all other attributes
                                other_attrs = {k: v for k, v in attrs.items() if k not in ['displayName', 'code', 'value', 'codeSystemName']}
                                if other_attrs:
                                    text_output.append(f"    Other Attributes: {other_attrs}")
                
                text_output.append("")
            
            text_output.append("")
        
        formatted_text = '\n'.join(text_output)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(formatted_text)
        
        return formatted_text
    
    @staticmethod
    def _group_related_fields(fields: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group related fields together (e.g., code with displayName and codeSystemName)."""
        grouped = {}
        
        # Find base fields (code, value, methodCode, etc.)
        base_fields = set()
        for field_name in fields.keys():
            if '/' in field_name:
                # For paths like "code/code", "code/displayName", "methodCode/code"
                base_field = field_name.rsplit('/', 1)[0]  # Get everything before the last /
                base_fields.add(base_field)
            else:
                base_fields.add(field_name)
        
        for base_field in base_fields:
            # Collect all variations of this base field
            related_fields = {}
            for field_name, field_data in fields.items():
                if field_name.startswith(base_field + '/') or field_name == base_field:
                    if '/' in field_name:
                        attr_type = field_name.rsplit('/', 1)[1]  # Get the part after the last /
                    else:
                        attr_type = 'value'
                    related_fields[attr_type] = field_data
            
            if related_fields:
                # Combine related attributes for better readability
                combined_items = OutputFormatter._combine_related_attributes(related_fields)
                grouped[base_field] = combined_items
        
        return grouped
    
    @staticmethod
    def _combine_related_attributes(related_fields: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Combine related attributes (code, displayName, codeSystemName) into single items."""
        combined = []
        
        # Get the primary field (usually 'code' or 'value')
        primary_field = None
        for field_type in ['code', 'value']:
            if field_type in related_fields:
                primary_field = field_type
                break
        
        if not primary_field:
            # If no primary field, just return the first available field
            for field_type, field_data in related_fields.items():
                combined.extend(field_data)
            return combined
        
        primary_data = related_fields[primary_field]
        
        # For each primary item, try to find corresponding displayName and codeSystemName
        for i, primary_item in enumerate(primary_data):
            enhanced_item = primary_item.copy()
            
            # Add related displayName if available
            if 'displayName' in related_fields and i < len(related_fields['displayName']):
                display_item = related_fields['displayName'][i]
                if 'attribute_value' in display_item:
                    enhanced_item['related_displayName'] = display_item['attribute_value']
                elif 'attributes' in display_item and 'displayName' in display_item['attributes']:
                    enhanced_item['related_displayName'] = display_item['attributes']['displayName']
            
            # Add related codeSystemName if available
            if 'codeSystemName' in related_fields and i < len(related_fields['codeSystemName']):
                system_item = related_fields['codeSystemName'][i]
                if 'attribute_value' in system_item:
                    enhanced_item['related_codeSystemName'] = system_item['attribute_value']
                elif 'attributes' in system_item and 'codeSystemName' in system_item['attributes']:
                    enhanced_item['related_codeSystemName'] = system_item['attributes']['codeSystemName']
            
            combined.append(enhanced_item)
        
        # If we have displayName or codeSystemName fields but no primary field matches,
        # or if there are more displayName/codeSystemName entries than primary entries,
        # include the remaining items separately
        if 'displayName' in related_fields:
            for i in range(len(primary_data), len(related_fields['displayName'])):
                combined.append(related_fields['displayName'][i])
        
        if 'codeSystemName' in related_fields:
            for i in range(len(primary_data), len(related_fields['codeSystemName'])):
                combined.append(related_fields['codeSystemName'][i])
        
        return combined

def main():
    """Main function to run the CDA Element Finder tool."""
    parser = argparse.ArgumentParser(
        description='Find elements in CDA XML using XPath reference document'
    )
    parser.add_argument('xml_file', help='Path to the CDA XML file')
    parser.add_argument('--xpath-ref', help='Path to XPath reference file (optional)')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--format', '-f', choices=['json', 'csv', 'text'], 
                       default='json', help='Output format (default: json)')
    parser.add_argument('--auto-group', action='store_true', 
                       help='Automatically group XPath expressions by templateId')
    parser.add_argument('--show-both', action='store_true',
                       help='Show both individual and grouped results')
    parser.add_argument('--demo-grouped', action='store_true',
                       help='Run demonstration of grouped problem observations functionality')
    
    args = parser.parse_args()
    
    try:
        # Initialize components
        xpath_parser = XPathParser()
        element_finder = CDAElementFinder()
        
        # Handle demo-grouped option
        if args.demo_grouped:
            print("Running grouped problem observations demonstration...")
            element_finder.demonstrate_grouped_problem_observations(args.xml_file)
            return
        
        # Parse XPath reference document
        if args.xpath_ref:
            with open(args.xpath_ref, 'r', encoding='utf-8') as f:
                xpath_content = f.read()
        else:
            # Use embedded XPath patterns from the reference document
            xpath_content = """
            ClinicalDocument/effectiveTime/@value
            ClinicalDocument/recordTarget/patientRole/patient/name
            ClinicalDocument/recordTarget/patientRole/patient/birthTime/@value  
            ClinicalDocument/recordTarget/patientRole/patient/administrativeGenderCode/@code
            observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/code/@code
            observation[templateId[@root='2.16.840.1.113883.10.20.22.4.2']]/value/@value
            """
        
        print("Parsing XPath reference document...")
        xpath_entries = xpath_parser.parse_xpath_reference(xpath_content)
        print(f"Found {len(xpath_entries)} XPath expressions")
        
        # Initialize formatter
        formatter = OutputFormatter()
        
        # Handle auto-grouping option
        if args.auto_group:
            print(f"Processing CDA XML file with auto-grouping: {args.xml_file}")
            
            if args.show_both:
                # Show both individual and grouped results
                print("\n" + "="*50)
                print("INDIVIDUAL RESULTS")
                print("="*50)
                
                # First determine which XPath expressions can be grouped
                grouped_entries = element_finder.auto_group_xpath_entries(xpath_entries)
                
                # Get ungrouped XPath expressions (those without templateId)
                ungrouped_xpath_entries = grouped_entries.get('ungrouped', [])
                
                # Find individual elements only for ungrouped XPaths
                individual_results = element_finder.find_elements(args.xml_file, ungrouped_xpath_entries)
                
                # Display individual results
                if args.format == 'text':
                    individual_output = formatter.format_text(individual_results)
                    print(individual_output)
                else:
                    individual_output = formatter.format_json(individual_results)
                    print(individual_output)
                
                print(f"\nIndividual results: Found {len([r for r in individual_results if r['found']])} matching elements.")
                
                print("\n" + "="*50)
                print("GROUPED RESULTS")
                print("="*50)
                
                # Find grouped elements
                grouped_results = element_finder.find_elements_with_auto_grouping(args.xml_file, xpath_entries)
                
                # Display grouped results
                if args.format == 'text':
                    grouped_output = formatter.format_grouped_text(grouped_results)
                    print(grouped_output)
                else:
                    grouped_output = formatter.format_grouped_json(grouped_results)
                    print(grouped_output)
                
                total_instances = sum(len(group['instances']) for group in grouped_results)
                print(f"\nGrouped results: Found {total_instances} instances across {len(grouped_results)} template groups.")
                
                # Handle file output
                if args.output:
                    combined_output = {
                        'individual_results': individual_results,
                        'grouped_results': grouped_results,
                        'summary': {
                            'individual_matches': len([r for r in individual_results if r['found']]),
                            'grouped_instances': total_instances,
                            'template_groups': len(grouped_results)
                        }
                    }
                    
                    if args.format == 'json':
                        with open(args.output, 'w', encoding='utf-8') as f:
                            json.dump(combined_output, f, indent=2, ensure_ascii=False)
                    elif args.format == 'text':
                        with open(args.output, 'w', encoding='utf-8') as f:
                            f.write("INDIVIDUAL RESULTS\n")
                            f.write("="*50 + "\n")
                            f.write(formatter.format_text(individual_results))
                            f.write("\n\nGROUPED RESULTS\n")
                            f.write("="*50 + "\n")
                            f.write(formatter.format_grouped_text(grouped_results))
                    
                    print(f"\nCombined results saved to: {args.output}")
            else:
                # Show only grouped results
                grouped_results = element_finder.find_elements_with_auto_grouping(args.xml_file, xpath_entries)
                
                # Format and output grouped results
                if args.format == 'json':
                    output = formatter.format_grouped_json(grouped_results, args.output)
                    if not args.output:
                        print(output)
                elif args.format == 'text':
                    output = formatter.format_grouped_text(grouped_results, args.output)
                    if not args.output:
                        print(output)
                
                total_instances = sum(len(group['instances']) for group in grouped_results)
                print(f"\nProcessing complete. Found {total_instances} instances across {len(grouped_results)} template groups.")
        else:
            # Standard individual processing
            print(f"Processing CDA XML file: {args.xml_file}")
            results = element_finder.find_elements(args.xml_file, xpath_entries)
            
            # Format and output results
            if args.format == 'json':
                output = formatter.format_json(results, args.output)
                if not args.output:
                    print(output)
            elif args.format == 'csv':
                output = formatter.format_csv(results, args.output)
                if output:
                    print(output)
            elif args.format == 'text':
                output = formatter.format_text(results, args.output)  
                if not args.output:
                    print(output)
            
            print(f"\nProcessing complete. Found {len([r for r in results if r['found']])} matching elements.")
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()