"""
Gemini API Configuration Module

Handles initialization and configuration of Google Generative AI (Gemini) for
enhanced entity and relation extraction in the Knowledge Graph Builder.
"""
from __future__ import annotations

import os
from typing import Any

import google.generativeai as genai


class GeminiConfig:
    """Manages Gemini API configuration and client initialization."""
    
    def __init__(self) -> None:
        self._model = None
        self._api_key = None
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize Gemini API with API key from environment."""
        self._api_key = os.environ.get("GEMINI_API_KEY")
        if not self._api_key:
            print("Warning: GEMINI_API_KEY environment variable not set.")
            print("Gemini API features will be disabled.")
            return
        
        try:
            genai.configure(api_key=self._api_key)
            # Use gemini-pro for text processing
            self._model = genai.GenerativeModel('gemini-pro')
            print("Gemini API initialized successfully.")
        except Exception as e:
            print(f"Error initializing Gemini API: {e}")
            self._model = None
    
    def is_available(self) -> bool:
        """Check if Gemini API is properly configured and available."""
        return self._model is not None and self._api_key is not None
    
    def get_model(self):
        """Get the configured Gemini model instance."""
        return self._model
    
    async def generate_entities_and_relations(self, text: str) -> dict[str, Any]:
        """
        Use Gemini to extract entities and relations from text.
        
        Args:
            text: Input text to process
            
        Returns:
            Dictionary containing entities and relations extracted by Gemini
        """
        if not self.is_available():
            return {"entities": [], "relations": [], "error": "Gemini API not available"}
        
        prompt = f"""
Extract entities and relationships from the following text. 
Return the results in a structured JSON format.

Text: "{text}"

Please extract:
1. Entities with their types (Person, Organization, Location, Event, Other)
2. Relationships between entities with relation types

Format your response as valid JSON:
{{
    "entities": [
        {{"text": "entity name", "type": "Person|Organization|Location|Event|Other"}}
    ],
    "relations": [
        {{"source": "entity1", "target": "entity2", "relation": "relationship_type"}}
    ]
}}

Focus on meaningful entities and clear relationships. Be concise but accurate.
"""
        
        try:
            response = self._model.generate_content(prompt)
            result_text = response.text
            
            # Try to parse the JSON response
            import json
            # Clean up the response to extract JSON
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_text = result_text[json_start:json_end]
                result = json.loads(json_text)
                return result
            else:
                return {"entities": [], "relations": [], "error": "Invalid JSON response"}
                
        except Exception as e:
            return {"entities": [], "relations": [], "error": f"Gemini API error: {str(e)}"}
    
    def enhance_extraction_with_gemini(self, spacy_entities: list[dict], spacy_relations: list[dict], text: str) -> dict[str, Any]:
        """
        Enhance spaCy extraction with Gemini API results.
        
        Args:
            spacy_entities: Entities extracted by spaCy
            spacy_relations: Relations extracted by spaCy  
            text: Original input text
            
        Returns:
            Enhanced entities and relations combining both approaches
        """
        if not self.is_available():
            return {
                "entities": spacy_entities,
                "relations": spacy_relations,
                "enhanced": False
            }
        
        try:
            # Get Gemini extraction
            gemini_result = self.generate_entities_and_relations(text)
            
            if "error" in gemini_result:
                return {
                    "entities": spacy_entities,
                    "relations": spacy_relations,
                    "enhanced": False,
                    "error": gemini_result["error"]
                }
            
            gemini_entities = gemini_result.get("entities", [])
            gemini_relations = gemini_result.get("relations", [])
            
            # Merge entities (prefer spaCy for entity types, add Gemini entities that are new)
            merged_entities = self._merge_entities(spacy_entities, gemini_entities)
            
            # Merge relations (combine both, remove duplicates)
            merged_relations = self._merge_relations(spacy_relations, gemini_relations)
            
            return {
                "entities": merged_entities,
                "relations": merged_relations,
                "enhanced": True,
                "gemini_entities": len(gemini_entities),
                "gemini_relations": len(gemini_relations)
            }
            
        except Exception as e:
            return {
                "entities": spacy_entities,
                "relations": spacy_relations,
                "enhanced": False,
                "error": f"Enhancement error: {str(e)}"
            }
    
    def _merge_entities(self, spacy_entities: list[dict], gemini_entities: list[dict]) -> list[dict]:
        """Merge spaCy and Gemini entities, removing duplicates."""
        merged = []
        seen_texts = set()
        
        # Add spaCy entities first (they have better type classification)
        for entity in spacy_entities:
            text_lower = entity.get("text", "").lower()
            if text_lower and text_lower not in seen_texts:
                merged.append(entity)
                seen_texts.add(text_lower)
        
        # Add Gemini entities that are new
        for entity in gemini_entities:
            text_lower = entity.get("text", "").lower()
            if text_lower and text_lower not in seen_texts:
                # Convert Gemini entity format to match spaCy format
                merged_entity = {
                    "text": entity.get("text", ""),
                    "label": entity.get("type", "Other"),
                    "type": entity.get("type", "Other")
                }
                merged.append(merged_entity)
                seen_texts.add(text_lower)
        
        return merged
    
    def _merge_relations(self, spacy_relations: list[dict], gemini_relations: list[dict]) -> list[dict]:
        """Merge spaCy and Gemini relations, removing duplicates."""
        merged = []
        seen_relations = set()
        
        # Add spaCy relations
        for relation in spacy_relations:
            key = (
                relation.get("source", "").lower(),
                relation.get("target", "").lower(), 
                relation.get("relation", "").lower()
            )
            if key not in seen_relations:
                merged.append(relation)
                seen_relations.add(key)
        
        # Add Gemini relations that are new
        for relation in gemini_relations:
            key = (
                relation.get("source", "").lower(),
                relation.get("target", "").lower(),
                relation.get("relation", "").lower()
            )
            if key not in seen_relations:
                # Ensure relation has required fields
                merged_relation = {
                    "source": relation.get("source", ""),
                    "target": relation.get("target", ""),
                    "relation": relation.get("relation", "related_to"),
                    "passive": False
                }
                merged.append(merged_relation)
                seen_relations.add(key)
        
        return merged
    
    def answer_question_with_gemini(self, question: str, graph_data: dict[str, Any], original_text: str) -> dict[str, Any]:
        """
        Use Gemini to answer questions about the knowledge graph and original text.
        
        Args:
            question: User's question
            graph_data: Knowledge graph data with nodes and edges
            original_text: Original input text for context
            
        Returns:
            Dictionary with answer and metadata
        """
        if not self.is_available():
            return {"answer": None, "error": "Gemini API not available", "method": "gemini_failed"}
        
        # Extract relevant information from graph
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        
        # Create a simplified representation of the graph
        graph_summary = self._create_graph_summary(nodes, edges)
        
        prompt = f"""
Based on the following knowledge graph and original text, please answer the user's question.

ORIGINAL TEXT:
"{original_text}"

KNOWLEDGE GRAPH:
{graph_summary}

USER QUESTION:
"{question}"

Please provide a direct and accurate answer based on the information available. If the answer cannot be found in the provided text and knowledge graph, say "Answer not found in the provided information."

Be concise but complete. Use only the information provided above.
"""
        
        try:
            response = self._model.generate_content(prompt)
            answer = response.text.strip()
            
            # Check if answer indicates not found
            if "not found" in answer.lower() or "cannot" in answer.lower() or "don't have" in answer.lower():
                return {"answer": None, "error": "Answer not found", "method": "gemini_not_found"}
            
            return {"answer": answer, "method": "gemini", "confidence": "high"}
            
        except Exception as e:
            return {"answer": None, "error": f"Gemini API error: {str(e)}", "method": "gemini_error"}
    
    def _create_graph_summary(self, nodes: list[dict], edges: list[dict]) -> str:
        """Create a readable summary of the knowledge graph for Gemini."""
        summary_parts = []
        
        # Add entities
        if nodes:
            entity_types = {}
            for node in nodes:
                node_type = node.get("type", "Other")
                if node_type not in entity_types:
                    entity_types[node_type] = []
                entity_types[node_type].append(node.get("name", ""))
            
            summary_parts.append("ENTITIES:")
            for entity_type, entities in entity_types.items():
                if entities:
                    summary_parts.append(f"  {entity_type}: {', '.join(entities[:10])}")
                    if len(entities) > 10:
                        summary_parts.append(f"    (and {len(entities) - 10} more {entity_type.lower()})")
        
        # Add relationships
        if edges:
            summary_parts.append("\nRELATIONSHIPS:")
            for edge in edges[:20]:  # Limit to first 20 edges to avoid token limits
                source = edge.get("source", "")
                target = edge.get("target", "")
                relation = edge.get("relation", "")
                if source and target and relation:
                    summary_parts.append(f"  {source} -> {relation} -> {target}")
            
            if len(edges) > 20:
                summary_parts.append(f"  (and {len(edges) - 20} more relationships)")
        
        return "\n".join(summary_parts)


# Global instance for reuse across the application
gemini_config = GeminiConfig()
