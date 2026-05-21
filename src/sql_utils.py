from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tables import Base, Towns, Weekends

engine = create_engine(
    "sqlite:///data/local.db", echo=False
)  # echo=True shows SQL logs


def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


def create_tables():

    Base.metadata.create_all(engine)


def populate_weekends():

    session = next(get_db())

    if session.query(Weekends).first():
        session.close()
        return

    # Example: Populate weekends with some dummy data
    weekends = [Weekends(date="2026-05-30")]

    for weekend in weekends:
        session.add(weekend)

    session.commit()
    session.close()


def populate_towns():

    session = next(get_db())

    if session.query(Towns).first():
        session.close()
        return

    raw_data = """
771,West Dover,Vermont,50000,0.0%
772,New City,New York,50000,0.0%
773,Batavia,New York,50000,-0.5%
748,Commerce City,Colorado,49799,135.4%
749,Monroe,Louisiana,49761,-6.1%
750,Cerritos,California,49707,-3.6%
751,Downers Grove,Illinois,49670,0.0%
752,Coral Gables,Florida,49631,16.1%
753,Wilson,North Carolina,49628,10.1%
754,Niagara Falls,New York,49468,-10.8%
755,Poway,California,49417,2.4%
756,Edina,Minnesota,49376,4.1%
757,Cuyahoga Falls,Ohio,49267,-0.2%
758,Rancho Santa Margarita,California,49228,4.6%
759,Harrisburg,Pennsylvania,49188,0.6%
760,Huntington,West Virginia,49177,-5.0%
761,La Mirada,California,49133,4.6%
762,Cypress,California,49087,5.3%
763,Caldwell,Idaho,48957,77.1%
764,Logan,Utah,48913,14.5%
765,Galveston,Texas,48733,-15.2%
766,Sheboygan,Wisconsin,48725,-3.9%
767,Middletown,Ohio,48630,-5.7%
768,Murray,Utah,48612,6.6%
769,Roswell,New Mexico,48611,7.5%
770,Parker,Colorado,48608,96.4%
771,Bedford,Texas,48592,2.9%
772,East Lansing,Michigan,48554,4.2%
773,Methuen,Massachusetts,48514,10.3%
774,Covina,California,48508,3.3%
775,Alexandria,Louisiana,48426,4.1%
776,Olympia,Washington,48338,12.1%
777,Euclid,Ohio,48139,-8.4%
778,Mishawaka,Indiana,47989,2.0%
779,Salina,Kansas,47846,4.5%
780,Azusa,California,47842,6.7%
781,Newark,Ohio,47777,3.1%
782,Chesterfield,Missouri,47749,1.9%
783,Leesburg,Virginia,47673,66.0%
784,Dunwoody,Georgia,47591,
785,Hattiesburg,Mississippi,47556,3.1%
786,Roseville,Michigan,47555,-1.0%
787,Bonita Springs,Florida,47547,43.8%
788,Portage,Michigan,47523,5.7%
789,St. Louis Park,Minnesota,47411,7.3%
790,Collierville,Tennessee,47333,43.4%
791,Middletown,Connecticut,47333,3.6%
792,Stillwater,Oklahoma,47186,20.1%
793,East Providence,Rhode Island,47149,-3.3%
794,Lawrence,Indiana,47135,20.5%
795,Wauwatosa,Wisconsin,47134,0.0%
796,Mentor,Ohio,46979,-6.6%
797,Ceres,California,46714,34.0%
798,Cedar Hill,Texas,46663,42.4%
799,Mansfield,Ohio,46454,-10.1%
800,Binghamton,New York,46444,-1.7%
801,Coeur d'Alene,Idaho,46402,32.8%
802,San Luis Obispo,California,46377,4.4%
803,Minot,North Dakota,46321,26.6%
804,Palm Springs,California,46281,7.7%
805,Pine Bluff,Arkansas,46094,-16.2%
806,Texas City,Texas,46081,10.3%
807,Summerville,South Carolina,46074,62.9%
808,Twin Falls,Idaho,45981,31.5%
809,Jeffersonville,Indiana,45929,53.3%
810,San Jacinto,California,45851,91.8%
811,Madison,Alabama,45799,53.7%
812,Altoona,Pennsylvania,45796,-7.3%
813,Columbus,Indiana,45775,16.4%
814,Beavercreek,Ohio,45712,19.0%
815,Apopka,Florida,45587,63.9%
816,Elmhurst,Illinois,45556,5.7%
817,Maricopa,Arizona,45508,2503.4%
818,Farmington,New Mexico,45426,18.1%
819,Glenview,Illinois,45417,5.2%
820,Cleveland Heights,Ohio,45394,-10.3%
821,Draper,Utah,45285,77.4%
822,Lincoln,California,45237,285.2%
823,Sierra Vista,Arizona,45129,19.3%
824,Lacey,Washington,44919,41.7%
825,Biloxi,Mississippi,44820,-11.5%
826,Strongsville,Ohio,44730,1.9%
827,Barnstable Town,Massachusetts,44641,-7.1%
828,Wylie,Texas,44575,185.2%
829,Sayreville,New Jersey,44412,9.6%
830,Kannapolis,North Carolina,44359,18.6%
831,Charlottesville,Virginia,44349,10.5%
832,Littleton,Colorado,44275,9.4%
833,Titusville,Florida,44206,7.8%
834,Hackensack,New Jersey,44113,2.9%
835,Newark,California,44096,3.3%
836,Pittsfield,Massachusetts,44057,-3.6%
837,York,Pennsylvania,43935,6.4%
838,Lombard,Illinois,43907,2.9%
839,Attleboro,Massachusetts,43886,4.6%
840,DeKalb,Illinois,43849,11.8%
841,Blacksburg,Virginia,43609,9.4%
842,Dublin,Ohio,43607,37.6%
843,Haltom City,Texas,43580,11.4%
844,Lompoc,California,43509,5.5%
845,El Centro,California,43363,13.7%
846,Danville,California,43341,3.7%
847,Jefferson City,Missouri,43330,6.7%
848,Cutler Bay,Florida,43328,42.9%
849,Oakland Park,Florida,43286,2.7%
850,North Miami Beach,Florida,43250,3.6%
851,Freeport,New York,43167,-1.4%
852,Moline,Illinois,43116,-1.9%
853,Coachella,California,43092,88.4%
854,Fort Pierce,Florida,43074,6.9%
855,Smyrna,Tennessee,43060,54.9%
856,Bountiful,Utah,43023,3.9%
857,Fond du Lac,Wisconsin,42970,1.7%
858,Everett,Massachusetts,42935,12.1%
859,Danville,Virginia,42907,-11.0%
860,Keller,Texas,42907,53.3%
861,Belleville,Illinois,42895,1.2%
862,Bell Gardens,California,42889,-2.7%
863,Cleveland,Tennessee,42774,14.1%
864,North Lauderdale,Florida,42757,10.8%
865,Fairfield,Ohio,42635,1.2%
866,Salem,Massachusetts,42544,5.1%
867,Rancho Palos Verdes,California,42448,2.9%
868,San Bruno,California,42443,5.6%
869,Concord,New Hampshire,42419,4.1%
870,Burlington,Vermont,42284,6.1%
871,Apex,North Carolina,42214,98.8%
872,Midland,Michigan,42181,0.9%
873,Altamonte Springs,Florida,42150,2.0%
874,Hutchinson,Kansas,41889,0.1%
875,Buffalo Grove,Illinois,41778,-3.4%
876,Urbandale,Iowa,41776,41.5%
877,State College,Pennsylvania,41757,8.7%
878,Urbana,Illinois,41752,10.3%
879,Plainfield,Illinois,41734,203.6%
880,Manassas,Virginia,41705,19.5%
881,Bartlett,Illinois,41679,13.1%
882,Kearny,New Jersey,41664,2.8%
883,Oro Valley,Arizona,41627,27.0%
884,Findlay,Ohio,41512,5.8%
885,Rohnert Park,California,41398,0.0%
887,Westfield,Massachusetts,41301,3.0%
886,Linden,New Jersey,41301,4.7%
888,Sumter,South Carolina,41190,1.3%
889,Wilkes-Barre,Pennsylvania,41108,-4.3%
890,Woonsocket,Rhode Island,41026,-5.2%
891,Leominster,Massachusetts,41002,-1.1%
892,Shelton,Connecticut,40999,7.3%
893,Brea,California,40963,15.2%
894,Covington,Kentucky,40956,-4.7%
895,Rockwall,Texas,40922,117.2%
896,Meridian,Mississippi,40921,-0.9%
897,Riverton,Utah,40921,61.6%
898,St. Cloud,Florida,40918,86.2%
899,Quincy,Illinois,40915,0.5%
900,Morgan Hill,California,40836,19.5%
901,Warren,Ohio,40768,-15.2%
902,Edmonds,Washington,40727,2.9%
903,Burleson,Texas,40714,85.3%
904,Beverly,Massachusetts,40664,2.0%
905,Mankato,Minnesota,40641,24.7%
906,Hagerstown,Maryland,40612,10.4%
907,Prescott,Arizona,40590,18.1%
908,Campbell,California,40584,4.2%
909,Cedar Falls,Iowa,40566,12.0%
910,Beaumont,California,40481,254.5%
911,La Puente,California,40435,-1.6%
912,Crystal Lake,Illinois,40388,5.3%
913,Fitchburg,Massachusetts,40383,3.5%
914,Carol Stream,Illinois,40379,-0.2%
915,Hickory,North Carolina,40361,7.0%
916,Streamwood,Illinois,40351,10.1%
917,Norwich,Connecticut,40347,11.6%
918,Coppell,Texas,40342,10.3%
919,San Gabriel,California,40275,0.9%
920,Holyoke,Massachusetts,40249,0.9%
921,Bentonville,Arkansas,40167,97.7%
922,Florence,Alabama,40059,10.2%
923,Peachtree Corners,Georgia,40059,
924,Brentwood,Tennessee,40021,51.9%
925,Bozeman,Montana,39860,41.9%
926,New Berlin,Wisconsin,39834,3.6%
927,Goose Creek,South Carolina,39823,26.1%
928,Huntsville,Texas,39795,13.2%
929,Prescott Valley,Arizona,39791,62.9%
930,Maplewood,Minnesota,39765,12.3%
931,Romeoville,Illinois,39650,79.5%
932,Duncanville,Texas,39605,9.7%
933,Atlantic City,New Jersey,39551,-2.2%
934,Clovis,New Mexico,39508,21.3%
935,The Colony,Texas,39458,45.7%
936,Culver City,California,39428,1.3%
937,Marlborough,Massachusetts,39414,7.6%
938,Hilton Head Island,South Carolina,39412,16.0%
939,Moorhead,Minnesota,39398,21.3%
940,Calexico,California,39389,44.0%
941,Bullhead City,Arizona,39383,15.9%
942,Germantown,Tennessee,39375,4.1%
943,La Quinta,California,39331,59.9%
944,Lancaster,Ohio,39325,10.7%
945,Wausau,Wisconsin,39309,1.7%
946,Sherman,Texas,39296,11.6%
947,Ocoee,Florida,39172,57.9%
948,Shakopee,Minnesota,39167,85.7%
949,Woburn,Massachusetts,39083,4.4%
950,Bremerton,Washington,39056,4.9%
951,Rock Island,Illinois,38877,-1.9%
952,Muskogee,Oklahoma,38863,-0.7%
953,Cape Girardeau,Missouri,38816,9.4%
954,Annapolis,Maryland,38722,7.6%
955,Greenacres,Florida,38696,35.5%
956,Ormond Beach,Florida,38661,5.8%
957,Hallandale Beach,Florida,38632,12.4%
958,Stanton,California,38623,2.8%
959,Puyallup,Washington,38609,11.8%
960,Pacifica,California,38606,0.5%
961,Hanover Park,Illinois,38510,0.6%
962,Hurst,Texas,38448,5.8%
963,Lima,Ohio,38355,-8.1%
964,Marana,Arizona,38290,166.2%
965,Carpentersville,Illinois,38241,22.8%
966,Oakley,California,38194,47.7%
967,Huber Heights,Ohio,38142,-0.2%
968,Lancaster,Texas,38071,46.4%
969,Montclair,California,38027,12.1%
970,Wheeling,Illinois,38015,4.8%
971,Brookfield,Wisconsin,37999,-1.9%
972,Park Ridge,Illinois,37839,0.1%
973,Florence,South Carolina,37792,19.8%
974,Roy,Utah,37733,13.3%
975,Winter Garden,Florida,37711,142.5%
976,Chelsea,Massachusetts,37670,7.3%
977,Valley Stream,New York,37659,3.6%
978,Spartanburg,South Carolina,37647,-6.2%
979,Lake Oswego,Oregon,37610,5.3%
980,Friendswood,Texas,37587,28.6%
981,Westerville,Ohio,37530,5.7%
982,Northglenn,Colorado,37499,15.5%
983,Phenix City,Alabama,37498,31.9%
984,Grove City,Ohio,37490,35.6%
985,Texarkana,Texas,37442,7.4%
986,Addison,Illinois,37385,2.6%
987,Dover,Delaware,37366,16.0%
988,Lincoln Park,Michigan,37313,-6.7%
989,Calumet City,Illinois,37240,-4.5%
990,Muskegon,Michigan,37213,-7.1%
991,Aventura,Florida,37199,47.2%
992,Martinez,California,37165,3.4%
993,Greenfield,Wisconsin,37159,4.8%
994,Apache Junction,Arizona,37130,15.7%
995,Monrovia,California,37101,0.2%
996,Weslaco,Texas,37093,28.8%
997,Keizer,Oregon,37064,14.4%
998,Spanish Fork,Utah,36956,78.1%
999,Beloit,Wisconsin,36888,2.9%
1000,Panama City,Florida,36877,0.1%
    """

    raw_data_lines = raw_data.strip().split("\n")[1:]  # Skip header line

    for line in raw_data_lines:
        id, name, state, population, growth_rate = line.split(",")
        town = Towns(name=name, state=state, population=int(population))
        print(f"Adding town: {name}, {state} with population {population}")
        session.add(town)

    session.commit()
    session.close()
