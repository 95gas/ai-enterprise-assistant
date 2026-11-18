from typing import List, Literal, Tuple, Type, Any


class SchemaHandler:
    """
    Handles schema definitions for knowledge graph validation, including entities, relations,
    and validation schemas.
    """
    @staticmethod
    def get_validation_schema():
        """
        Retrieve the validation schema defining valid triples in the knowledge graph.

        :return: A list of tuples representing valid (entity, relation, entity) triples.
        """
        return {
                "PRODUCT": ["USED_BY", "USED_FOR",   "PART_OF"],
                "MARKET": ["LOCATED_IN",  "PART_OF", "REPRESENTS"],
                "TECHNOLOGY": ["USED_BY", "USED_FOR", "LOCATED_IN", "PART_OF"],
                "EVENT": ["LOCATED_IN", "PART_OF",  "REPRESENTS", "HAPPENED"],
                "CONCEPT": ["USED_BY", "USED_FOR", "INFLUENCES", "REPRESENTS",  "EXPLAINED"],
                "ORGANIZATION": ["LOCATED_IN", "PART_OF", "SUPPORTS"],
                "PERSON": ["BORN_IN", "IS_FOUNDER_OF", "WORK_FOR", "DIED_IN", "WORKED_ON", "CREATED", "WROTE", "IS_HEADER_OF"],
                "LOCATION": ["LOCATED_IN", "PART_OF", "REPRESENTS", "MENTIONS"],
                "DOCUMENT": [  "REFERENCES", "SUPPORTS", "SUMMARIZES", "CREATED", "RELEASED"],
                "LAW_OF_REFERENCE": ["CREATED", "REPRESENTS", "REGULATES", "RELEASED"]
            }


    @staticmethod
    def get_entities_prop()->List[Tuple[str, str]]:
        return [
                ("PERSON", "An individual or a group of people, such as a first or full name, author, or historical figure."),
                ("STATISTIC", "A numerical value representing data, such as percentages, averages, or trends."),
                ("EVENT", "An occurrence or happening, such as a meeting, conference, or historical incident."),
                ("ORGANIZATION", "A structured group, such as a company, institution, or nonprofit entity."),
                ("CONCEPT", "A theory, discussion, research, analysis, principle or explanation."),
                ("DOCUMENT", "A written, digital, or printed file containing information, such as reports, articles, books, or legal texts."),
                ("QUESTION", "An inquiry or request for information, typically in interrogative form."),
                ("ANSWER", "A response or solution to a given question, problem, or inquiry."),
                ("TASK", "A specific activity or duty that needs to be completed, often within a given timeframe."),
                ("PRODUCT", "A tangible or intangible item designed for consumption, sale, or use."),
                ("MARKET", "An economic system where goods, services, and assets are exchanged, including customer segments."),
                ("TECHNOLOGY", "Tools, techniques, and systems developed to solve problems or improve efficiency."),
                ("LOCATION", "A geographic place or position, such as a city, country, or specific site."),
                ("TIME", "A reference to temporal aspects, including dates, times, durations, or historical periods."),
                ("LAW_OF_REFERENCE", "A legal rule, regulation, or principle that serves as a guideline or precedent.")
            ]



    @staticmethod
    def get_entities() :
        """
        Retrieve the list of possible entity types for the knowledge graph.
        :return: A list of the valid entity types.
        """
        return Literal[
            "PERSON", "STATISTIC", "EVENT",
            "ORGANIZATION", "CONCEPT", "DOCUMENT",
            "QUESTION", "ANSWER", "TASK", "PRODUCT", "MARKET",
            "TECHNOLOGY", "LOCATION", "TIME", "LAW_OF_REFERENCE"
        ]

    @staticmethod
    def get_relations():
        """
        Retrieve the list of possible relation types for the knowledge graph.
        :return: A list of strings.
        """
        return Literal[
                "PART_OF", "IS_HEADER_OF",
                "LOCATED_IN", "WROTE",
                "INFLUENCES", "REPRESENTS",
                 "REFERENCES", 
                "SUPPORTS", "SUMMARIZES",
                "USED_BY", "USED_FOR", "WORKED_ON", "BORN_IN",
                "DIED_IN", "IS_FOUNDER_OF", "WORK_FOR",
                "CREATED", "REGULATES", "RELEASED"
        ]

    @staticmethod
    def get_relations_props():
        """
        Retrieve the list of possible relation types for the knowledge graph.
        :return: A list of strings.
        """
        return [
                ("PART_OF", "Indicates that something is a component or subset of a larger whole."),
                ("IS_HEADER_OF", "Specifies that a person serves as a leading"),
                ("LOCATED_IN", "Indicates the geographic or spatial placement of an entity within a larger location."),
                ("WROTE", "Denotes authorship or contribution to a written work."),
                ("INFLUENCES", "Indicates an entity's impact on another in terms of ideas, actions, or outcomes."),
                ("REPRESENTS", "Signifies that an entity stands for or symbolizes another."),
                ("REFERENCES", "Denotes a citation or acknowledgment of another entity as a source."),
                ("SUPPORTS", "Indicates endorsement, assistance, or validation of another entity."),
                ("SUMMARIZES", "Denotes a condensed or simplified representation of another entity."),
                ("USED_BY", "Indicates that an entity is utilized or employed by another."),
                ("USED_FOR", "Denotes the purpose or function of an entity."),
                ("WORKED_ON", "Specifies that an individual or entity contributed effort to a project or task."),
                ("BORN_IN", "Indicates the birthplace or origin location of a person."),
                ("DIED_IN", "Specifies the place where an individual passed away."),
                ("IS_FOUNDER_OF", "Denotes that an individual established or initiated an organization or entity."),
                ("WORK_FOR", "Represents employment or professional association with an entity."),
                ("CREATED", "Indicates the act of bringing something into existence."),
                ("REGULATES", "Denotes governance, control, or enforcement over a system or entity."),
                ("RELEASED", "Specifies the act of making something available as or at a date."),
            ]
