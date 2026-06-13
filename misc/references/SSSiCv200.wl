(* ::Package:: *)
BeginPackage["SSSiCv100`"]
(* local "globals" *)
$SSSConnectionList = $SSSRulesUsed = {}; $SSSTagIndex = 0; (* create "globals" for later use *)
(* usage messages *)
SSSEvolve::usage="SSSEvolve[\!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\), \!\(\*StyleBox[\"n\",FontSlant->\"Italic\"]\)] "<>
"generates an additional \!\(\*StyleBox[\"n\",FontSlant->\"Italic\"]\) levels of indicated "<>
"\!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)(sequential substitution system), "<>
"which must have been previously created using SSSInitialize.  Use the option EarlyReturn -> True to allow early termination for "<>
"repeating cases.  (SSSSinglestep immediately returns anyway if the SSS is dead.)  In Loud mode, prints the current verdict, \"OK\" "<>
"means none known.  Values of \!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\) updated, with \"Evolution\" containing the tagless SSS, "<>
"\"ConnectionList\" the updated causal network connection list, etc.  mode can be Silent, Quiet, or Loud.";
	
SSSDisplay::usage="SSSDisplay[\!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\), \!\(\*StyleBox[\"opts\",FontSlant->\"Italic\"]\)] displays the sequential substitution system \!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\) and/or its causal network.  Use SSS (or SSSInitialize and SSSEvolve) to construct it first.
Options:
	Min -> n cuts off the display before the first n steps of the system.  (Separate values can be specified for SSSMin and NetMin.)
	Max -> n cuts off the display after the first n steps of the system.  (Separate values can be specified for SSSMax and NetMax.)
	VertexLabels -> Automatic (or \"Name\") | \"VertexWeight\" | \[Ellipsis]  labels vertices by node number or distance from origin, etc.
	HighlightMethod -> Dot | Frame | Number (or True) | None (or False) specifies how the matches in the SSS are highlighted. 
	ShowRule -> Bottom | Top | Left | Right | None (or False) specifies where to place the rulelist icon relative to the SSS visual display (if shown).  
	Sizes of display components are specified by the options NetSize, SSSSize, IconSize and ImageSize (which refers to the pane containing the SSS display and icon).
	NetMethod -> GraphPlot | LayeredGraphPlot | TreePlot | GraphPlot3D | All | NoSSS | list of methods, 
  where NoSSS generates no SSS display (causal network only) and the other choices specify how the causal network is to be shown.";

SSS::usage="SSS[\!\(\*
StyleBox[\"rule\",\nFontSlant->\"Italic\"]\)set\!\(\*
StyleBox[\",\",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\" \",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\"init\",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\",\",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\" \",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\"n\",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\",\",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\" \",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\"opts\",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\"]\",\nFontSlant->\"Italic\"]\)\!\(\*
StyleBox[\" \",\nFontSlant->\"Italic\"]\)creates and displays a sequential substitution system (SSS) and its causal network, using \!\(\*
StyleBox[\"ruleset\",\nFontSlant->\"Italic\"]\) (as a list of rules, or a RSS index), starting with the state \!\(\*
StyleBox[\"init\",\nFontSlant->\"Italic\"]\) (using string notation), allowing the SSS to evolve for \!\(\*
StyleBox[\"n\",\nFontSlant->\"Italic\"]\) steps.  If the initial state string is omitted, SSSInitialState is called to provide a sufficiently complex string.  Use the option EarlyReturn to give/deny permission to quit early if the SSS can be identified as dead or repeating.)  Use option Mode -> Silent to suppress display of the sessie. Any other options given are passed on to SSSDisplay.
(Returns a copy of the SSS that can then be displayed or manipulated without rebuilding, using SSSDisplay, SSSAnimate, or directly, looking at its keys, \"Evolution\" and \"Net\", etc.)";

SSSInteractiveDisplay::usage="SSSInteractiveDisplay[\!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\)] provides an interactive display of \!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\) and its causal network, with controls for easy adjustment of common options.  Click the button to create a SSSDisplay object with the selected options.";

SSSAnimate::usage="SSSAnimate[\!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\), \!\(\*StyleBox[\"opts\",FontSlant->\"Italic\"]\)] animates the display of the causal network of the sequential substitution system \!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\).  Use SSS (or SSSInitialize and SSSEvolve) to construct it first.  Takes all the options of SSSDisplay, with one modification:
VertexLabels -> \"Name\" (default) | \"VertexWeight\"  display the vertex name/index or its distance from the origin.";

FromReducedRankIndex::usage="Takes as argument a positive integer index, and returns the corresponding ruleset object of the form <|\"Index\"->_,\"QCode\"->_,\"RuleSet\"->_|>, to which can be applied any of the TestFor... functions, or SSS.";
FromReducedRankRuleSet::usage="Takes as argument a list of substitution rules, and returns the corresponding ruleset object of the form <|\"Index\"->_,\"QCode\"->_,\"RuleSet\"->_|>, to which can be applied any of the TestFor... functions, or SSS.";
FromReducedRankQuinaryCode::usage="Takes as argument a string containing a quinary code, and returns the corresponding ruleset object of the form <|\"Index\"->_,\"QCode\"->_,\"RuleSet\"->_|>, to which can be applied any of the TestFor... functions, or SSS.";
ToCanonical::usage="Replaces and permutes characters in a ruleset to form a functionally equivalent one in which the first character is \"A\", the first non-\"A\" character is \"B\", etc.  This canonical form may have a greater ruleset weight, but it is the easiest to identify.  Argument can be either a ruleset object or a list of substitution rules.  TestForRenamedRuleSet jumps over any non-canonical ruleset.)";
ToLeastWeight::usage="Replaces and permutes characters in a ruleset to form a functionally equivalent ruleset with the least weight, the first to appear in the enumeration.  In theory this could be the representative chosen for treatment, and others discarded, but currently the canonical form (in which the characters are introduced in strict alphabetical order) is used.  Argument can be either a ruleset object or a list of substitution rules.";
TestForConflictingRules::usage="TestForConflictingRules[\!\(\*
StyleBox[\"rs\",\nFontSlant->\"Italic\"]\)] checks whether the ruleset object \!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\) contains any cases of conflicting rules, and if so, returns the resolution ruleset object.  Returns {} if there is no conflict.";
TestForNonSoloIdentityRule::usage="TestForNonSoloIdentityRule[\!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\)] checks whether the ruleset object \!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\) is not a singleton rule and contains any identity rules, and if so, returns the resolution ruleset object.  Returns {} if there is no problem.";
TestForIdentityRule::usage="TestForIdentityRule[\!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\)] checks whether the ruleset object \!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\) contains any identity rules, and if so, returns the resolution ruleset object.  Returns {} if there is no identity rule.";
TestForRenamedRuleSet::usage="TestForRenamedRuleSet[\!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\)] checks whether the ruleset object \!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\) is already in canonical form, and if so, returns {}.  If not canonical, \!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\) is a renamed ruleset, one in a run of such rulesets that can be long-jumped over, in which case, the function returns the resolution ruleset object.";
TestForInitialSubstringRule::usage="TestForInitialSubstringRule[\!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\)] checks whether the first rule of ruleset object \!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\) is a substring rule, and if so, returns the resolution ruleset object.  Returns {} if there is no problem.";
TestForNonSoloInitialSubstringRule::usage="TestForNonSoloInitialSubstringRule[\!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\)] checks whether the ruleset object \!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\) is not a singleton rule and contains as its first rule a substring rule, and if so, returns the resolution ruleset object.  Returns {} if there is no problem.  (The only reason to use this function instead of TestForInitialSubstringRule is if you want to explicitly include singleton substring rule cases, including singleton identity rules.  A singleton substring rule case does not reduce to a simpler case, although it has the same causal network as a simpler singleton identity rule case.)";
TestForShorteningRuleSet::usage="TestForShorteningRuleSet[\!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\)] checks whether (1) none of the rules of the ruleset lengthen the state string, and (2) at least one of the rules shortens it.  In either case, the sessie will die out or the ruleset will reduce to a simpler case.  If applicable, the function returns the resolution ruleset object: next in enumeration order, no long-jump possible.  Returns {} if there is no problem.";
TestForUnbalancedRuleSet::usage="TestForUnbalancedRuleSet[\!\(\*StyleBox[\"rs\",FontSlant->\"Italic\"]\)] checks whether all characters that appear in the rules appear at least once on both sides.  Otherwise, the sessie will die out or the ruleset will reduce to a simpler case.  If applicable, the function returns the resolution ruleset object: next in enumeration order, no long-jump possible.  Returns {} if there is no problem.";
TestForAll::usage="TestForAll[\!\(\*
StyleBox[\"rs\",\nFontSlant->\"Italic\"]\)] tries to apply all reliable ruleset tests (TestForConflictingRules, TestForNonSoloIdentityRule, TestForRenamedRuleSet, TestForNonSoloInitialSubstringRule, TestForUnbalancedRuleSet, TestForShorteningRuleSet) to the ruleset object \!\(\*
StyleBox[\"rs\",\nFontSlant->\"Italic\"]\), returning the resolution ruleset object provided by the first applicable test.  Returns {} if none apply.";
(* sessie construction & display *)
FromAlpha[string_String] :=(ToCharacterCode[string]-65);  
ToAlpha[l:{___Integer}] := FromCharacterCode[l+65];
Attributes[s]=Flat;
SSSConvert[string_String] := s @@ FromAlpha[string];
SSSConvert[s[x___]] := ToAlpha[{x}];
SSSConvert::usage="Converts SSS (sequential substitution system) states between s- and string-formats, using the functions \!\(\*StyleBox[\"FromAlpha\",FontSlant->\"Italic\"]\) and \!\(\*StyleBox[\"ToAlpha\",FontSlant->\"Italic\"]\).";
SSSStrip[x_s] := SSSConvert[x[[All,1]]] /; MatrixQ[List@@x];    (* if dim=2, take only 1st component, and convert *)
SSSStrip[x_s] := ""  /; Length[List@@x]==0;     (* treat empty string case *) 
SSSStrip::usage="SSSStrip[\!\(\*StyleBox[\"state\",FontSlant->\"Italic\"]\)] strips out tags from a \!\(\*StyleBox[\"state\",FontSlant->\"Italic\"]\) given in tagged SSS (sequential substitution system) format and returns it in string format.";
ToCharacterWeights[s_String] := (1+FromAlpha[s]);
FromCharacterWeights[l:{___Integer}] := ToAlpha[l-1];
(* Note: To avoid breaking the ruleset (un-)rank functions, avoid the temptation to define:  
ToCharacterWeights[""] = 0;  FromCharacterWeights[{0}]="";  *)
StringWeight[s_String] := Plus @@ ToCharacterWeights[s];
RuleSetWeight[rs_List] := Plus @@ (StringWeight /@ Flatten[rs /. Rule->List]);
RuleSetLength[rs_List] := Plus @@ (StringLength /@ Flatten[rs /. Rule->List]);
myColorOptions[maxColor_Integer (* minimum 1 *) ]:=Sequence[ColorRules->{0->LightGray},
ColorFunction->(Hue[(#-1)/(Max[1,maxColor])]&),ColorFunctionScaling->False];
patternPrint[pattern_,mxClr_Integer,opts___] := ArrayPlot[{{##}}& @@pattern,myColorOptions[mxClr],Mesh->True,opts,ImageSize->{Automatic,20}];
SSSRuleIcon[(rule_String|rule_Rule|rule_RuleDelayed),x___]:=SSSRuleIcon[{rule},x];
SSSRuleIcon[rules_List,x___]:=SSSRuleIcon[Map[SSSConvert,rules,{-1}],x] /; !FreeQ[rules,_String,Infinity];
SSSRuleIcon[rules_List,mxClr_Integer:6,opts___] := Panel[Grid[Map[patternPrint[#,mxClr,opts]&,rules,{2}] /. 
{Rule[x_,y_]:>{x,"\[AlignmentMarker]->",y},RuleDelayed[x_,y_]:>{x,"\[AlignmentMarker]:>",y}}, (* invisible AlignmentMarkers! *)
Alignment->Left],"Substitution Rule"<>If[Length[rules]>1,"s:",":"]] /; FreeQ[rules,_String,Infinity];
SSSRuleIcon::usage="SSSRuleIcon[\!\(\*StyleBox[\"rule\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\"(\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\"s\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\")\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\",\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\"maxColor\",FontSlant->\"Italic\"]\)] generates an icon for a sequential substitution system (SSS) rule or set of rules.";
SSSNewRule[rulenum_Integer,(rule_Rule | rule_RuleDelayed)] := 
(* the tagged rule created will need valid versions of $SSSConnectionList, $SSSTagIndex, $SSSRulesUsed, and will change them!  It's up to the calling routine to load/unload these globals.  *)
Module[{lhs,rhs,lhsNames,newlhs,newrhs1,newrhs2},
{lhs,rhs}=List@@rule;
lhsNames = Table[Unique[lhsTag],{StringLength[lhs]}];
newlhs=ToString[s@@Transpose[{FromAlpha[lhs],ToString@#<>"_"& /@ lhsNames}]];
newrhs1=("AppendTo[$SSSConnectionList, "<>ToString[lhsNames]<>" -> $SSSTagIndex + "<>ToString[Range@StringLength@rhs-1]<>"]; ");
newrhs2=ToString[SSSConvert[rhs] /. n_Integer :> {n,"$SSSTagIndex++"}];
ToExpression[newlhs<>" :> ("<>"AppendTo[$SSSRulesUsed,"<>ToString@rulenum<>"];"<>newrhs1<>newrhs2<>")"]];
SSSNewRule[rules_List] := Append[MapIndexed[SSSNewRule[First[#2],#1]&,rules],___:>AppendTo[$SSSRulesUsed,0]];
SSSNewRule::usage= 
"SSSNewRule[\!\(\*StyleBox[\"rule\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\"(\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\"s\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\")\",FontSlant->\"Italic\"]\)\!\(\*StyleBox[\"]\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"generates\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"the\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"needed\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"rules\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"for\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"the\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"tagged\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\"SSS\",FontSlant->\"Plain\"]\)\!\(\*StyleBox[\" \",FontSlant->\"Plain\"]\)(sequential substitution system) from the \!\(\*StyleBox[\"ruleset\",FontSlant->\"Italic\"]\) of rules given in string-format: e.g., \"BA\"->\"ABA\"";
Options[SSSInitialize]={Mode->Silent};
SSSInitialize::usage = "\!\(\*StyleBox[\"variable\",FontSlant->\"Italic\"]\) = SSSInitialize[ruleset, string, (mode)] attempts to perform the necessary initializion steps to generate sequential substitution system (SSS) evolutions and networks,\nstarting with a ruleset (e.g., {\"BA\"->\"ABA\"}) and an initial state string (e.g., \"BABA\").  The True|False return value indicates whether initialization was successful.\n\nIf omitted, mode defaults to \"Silent\", suppressing the short error or success message.\n\nThe following global variables are reset by this operation:\n\n$SSSNet:\t\t\t\tthe causal network of the current SSS,\n$SSSInDegree:\t\t\tthe list of in-degrees for each node,\n$SSSOutDegreeActual:\t\tthe list of currently found out-degrees for each node,\n$SSSOutDegreePotential:\t\tthe list of maximum possible out-degrees for each node,\n$SSSOutDegreeRemaining:\tthe list of numbers of possible remaining out-connections for each node,\n$SSSConnectionList:\t\tthe current list of all causal network connections,\n$SSSDistance:\t\t\tthe list of minimum distances from the current node back to the starting node.\n$SSSTagIndex:\t\t\tthe current tag index being used,\n$SSSTEvolution:\t\t\tthe complete evolution of the tagged SSS so far,\n$SSSEvolution:\t\t\tthe stripped (tagless) version of $SSSTEvolution,\n$SSSRuleSet:\t\t\tthe ruleset used for creating the SSS,\n$SSSTRuleSet:\t\t\tthe version of $SSSRuleSet (created by the function SSSNewRule) used to build $SSSTEvolution,\n$SSSRuleSetWeight:\t\tthe total weight of $SSSRuleSet,\n$SSSRuleSetLength:\t\tthe total length of $SSSRuleSet,\n$SSSRulesUsed:\t\tthe list of rules used\n$SSSCellsDeleted:\t\tthe list of cells in the state string deleted at each step,\n$SSSVerdict:\t\t\tset to \"Dead\" | \"Repeating\" as soon as the future of the SSS becomes clear.";
SSSInitialize[rs:{___Rule},state_String,opts:OptionsPattern[] (* Mode -> Silent | Quiet | Loud *)] :=
Module[{ans=<|"Net"->{},"OutDegreePotential"->{},"OutDegreeRemaining"->{},"OutDegreeActual"-> {},
"InDegree"-> {},"ConnectionList"->{},"Verdict"->"OK", "RulesUsed"->{},"CellsDeleted"->{},
"Distance"->{0}|>}, (* initial setup *)
AssociateTo[ans,{
"MaxColor"->Max[Flatten[{6,ToCharacterWeights /@ Flatten[rs/.Rule->List]}]],
"TagIndex"->StringLength[state]+1,
"TEvolution"->{s@@Transpose[{#,Range[Length[#]]}& @ FromAlpha[state]]},
"Evolution"->{state}, "RuleSet"->rs, "TRuleSet"->SSSNewRule[rs],
"RuleSetWeight"->RuleSetWeight[rs], "RuleSetLength"->RuleSetLength[rs]
}];
{$SSSConnectionList, $SSSTagIndex, $SSSRulesUsed}={ans["ConnectionList"],ans["TagIndex"],ans["RulesUsed"]};
AppendTo[ans["TEvolution"],Last[ans["TEvolution"]]/.ans["TRuleSet"]];
{ans["ConnectionList"],ans["TagIndex"],ans["RulesUsed"]}={$SSSConnectionList, $SSSTagIndex, $SSSRulesUsed};
Switch[ Last[ans["RulesUsed"]], (* can also test if Length[ans["ConnectionList"]]==0 *)
0,ans["TEvolution"]=Most[ans["TEvolution"]]; (* toss last duplicate entry *)
      ans["Verdict"]="Dead";
      If[ OptionValue[Mode]==Loud,Print["Error: No evolution possible starting from \""<>state<>"\" using ruleset: ",rs]];
      Return[ans (* but already including "Verdict" = Dead *)],
_, AppendTo[ans["Evolution"],SSSStrip[Last[ans["TEvolution"]]]]; (* add last entry *)
       If[ OptionValue[Mode]==Loud,Print["Successful initialization of ruleset: ",rs,", evolution: ",ans["Evolution"]]]
];
(* updateDegrees: this code needed for both SSSInitialize and SSSSingleStep *)
AppendTo[ans["InDegree"],Length[ans["ConnectionList"][[-1,1]]]];  (* # cells killed by this event = in-degree *)
(* calculate potential outdegree of new event, append to list *)
AppendTo[ans["OutDegreePotential"],Length[ans["ConnectionList"][[-1,-1]]]]; (* # of cells created by last rule *)
AppendTo[ans["OutDegreeRemaining"],Last[ans["OutDegreePotential"]]];
AppendTo[ans["OutDegreeActual"],0];
AppendTo[ans["CellsDeleted"],Flatten[Position[ans["TEvolution"][[-2]],{_,#}]& /@ans["ConnectionList"][[-1,1]]]];  (* Note positions of entries with tags indicated, add to the list *)
(* end of duplicate code *)
ans  (* Return the association created *)
];
SSSSingleStep::usage=
"SSSSingleStep[\!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\)] performs a single step of the sequential substitution system \!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\) evolution (if not already dead), returning the \!\(\*StyleBox[\"sss\",FontSlant->\"Italic\"]\) object (which must be created by SSSInitialize first).";
SSSSingleStep[sss_Association] := Module[{ans=sss,cd, ri, pri, rs, prs,len,startingEvents, oda, odr},
If[ans["Verdict"]==="Dead",Return[ans]];  (* if already dead, do nothing, return *)
(* do the actual evolution step *)
{$SSSConnectionList, $SSSTagIndex, $SSSRulesUsed}={ans["ConnectionList"],ans["TagIndex"],ans["RulesUsed"]};
AppendTo[ans["TEvolution"],Last[ans["TEvolution"]]/.ans["TRuleSet"]];
{ans["ConnectionList"],ans["TagIndex"],ans["RulesUsed"]}={$SSSConnectionList, $SSSTagIndex, $SSSRulesUsed};
If[Last[ans["RulesUsed"]]==0,ans["Verdict"]="Dead"; 
ans["TEvolution"]=Most[ans["TEvolution"]]; 
Return[ans]
];
AppendTo[ans["Evolution"],SSSStrip[Last[ans["TEvolution"]]]];
If[!MatchQ[ans["Verdict"],"Repeating"],  (* to limit wasted time, don't do this if the verdict is already in! *)
If[Length[Flatten@Position[ans["Evolution"],Last[ans["Evolution"]]]]>1, ans["Verdict"]="Repeating"]
]; 
(* updateDegrees: this code needed for both SSSInitialize and SSSSingleStep *)
AppendTo[ans["InDegree"],Length[ans["ConnectionList"][[-1,1]]]];  (* # cells killed by this event = in-degree *)
(* calculate potential outdegree of new event, append to list *)
AppendTo[ans["OutDegreePotential"],Length[ans["ConnectionList"][[-1,-1]]]]; 
AppendTo[ans["OutDegreeRemaining"],Last[ans["OutDegreePotential"]]];
AppendTo[ans["OutDegreeActual"],0];
AppendTo[ans["CellsDeleted"],Flatten[Position[ans["TEvolution"][[-2]],{_,#}]& /@ans["ConnectionList"][[-1,1]]]];  (* Note positions of entries with tags indicated, add to the list *)
(* end of duplicate code *)
(* now the steps that are only done for non-initial steps, comparing to previous entries in ans["ConnectionList"]: *)
len=Length[ans["ConnectionList"]];
startingEvents=Flatten[If[Length[#]>0,First[First[#]],#]& /@ (Position[ans["ConnectionList"][[;;-2]],#]& /@ ans["ConnectionList"][[-1,1]])];
oda=ans["OutDegreeActual"];
oda[[#]]++& /@ startingEvents; (* update out-degee list for events involved *)
AssociateTo[ans,"OutDegreeActual"->oda];
odr=ans["OutDegreeRemaining"];
odr[[#]]--& /@ startingEvents; (* update out-degee list for events involved *)
AssociateTo[ans,"OutDegreeRemaining"->odr];
AssociateTo[ans,"Net"->Join[ans["Net"],#->len& /@ startingEvents]];           (* add new links to the causal network *)
AssociateTo[ans,"Distance"->Append[ans["Distance"],Min[ans["Distance"][[startingEvents]]]+1]];  (* Find minimum path length of cause nodes, add 1 for path lengths of result nodes *)
ans  (* Return the updated association *)
];
Options[SSSEvolve]={EarlyReturn->False, Mode->Silent};
SyntaxInformation[SSSEvolve]={"ArgumentsPattern"->{_, _, OptionsPattern[]}};
SSSEvolve[sss_Association,n_Integer/;n>0,opts:OptionsPattern[]] := Module[{ans=sss},
If[OptionValue[EarlyReturn] ,
Do[If[MatchQ[ans["Verdict"], ("Dead"|"Repeating")],Return[ans],ans=SSSSingleStep[ans]],{n}], (* check before each step *)
Do[ans=SSSSingleStep[ans],{n}]   (* just do it *)
];
If[OptionValue[Mode]==Loud,Print[ans["Verdict"]]];
ans
];
Options[SSSDisplay]=
{HighlightMethod->True,RulePlacement->Bottom,Mesh->True,NetSize->{Automatic,400},SSSSize->{Automatic,300},IconSize->{Automatic,20},ImageSize->Automatic,NetMethod->GraphPlot,
Max->\[Infinity],SSSMax->Automatic,NetMax->Automatic,
Min->1,SSSMin->Automatic,NetMin->Automatic, 
Sequence@@Union[Options[TreePlot],Options[GraphPlot],Options[GraphPlot3D],Options[LayeredGraphPlot]]};
SyntaxInformation[SSSDisplay]={"ArgumentsPattern"->{_, OptionsPattern[]}};
SSSDisplay[sss_Association, opts:OptionsPattern[]] := Module[{HlM,mesh,IcS,ImS,SS,NS,RP,NM,doGP,doLGP,doTP,doGP3D,doSSS,myNet,ans,cellsToHighlight,rulesApplied,mx,netmx,sssmx,mn,netmn,sssmn,hs,start,ev,vrtxs,net,grph,DE},
HlM =If[#===True,Number,#]& @ OptionValue[HighlightMethod]; 
RP=OptionValue[RulePlacement];
mesh=OptionValue[Mesh];
SS = OptionValue[SSSSize];
IcS = OptionValue[IconSize];
ImS = OptionValue[ImageSize];
NS = OptionValue[NetSize];
NM=OptionValue[NetMethod];
DE= OptionValue[DirectedEdges];
mx=OptionValue[Max];
If[mx===Automatic,mx=\[Infinity]];
sssmx=OptionValue[SSSMax]; 
If[sssmx===Automatic,sssmx=mx];
netmx=OptionValue[NetMax]; 
If[netmx===Automatic,netmx=mx];
mn=OptionValue[Min];
If[mn===Automatic,mn=1];
sssmn=OptionValue[SSSMin]; 
If[sssmn===Automatic,sssmn=mn];
netmn=OptionValue[NetMin]; 
If[netmn===Automatic,netmn=mn];
start=1;
vrtxs =Annotation[#,VertexWeight->sss["Distance"][[#]]]&/@Range[Max[start,netmn],Min[netmx,Length[sss["Distance"]]]];
net=(Select[sss["Net"],And@@Thread[Max[start,netmn]<=List@@#<=netmx]&] /. n_Integer:>(n+1-start));
(*
If[UD||(DM<\[Infinity]),net=(net /.nn_Integer:>Subscript[sss["Distance"][[nn]],Style[nn,Tiny]])];
If[DM<\[Infinity],
net=Cases[net,r:Rule[Subscript[_?(#<=DM&),_],Subscript[_?(#<=DM&),_]]:> r];
If[!UD,net=(net /. Subscript[_,Style[n_Integer,_]]:>n)]
];
*)
grph=Graph[vrtxs,net,DirectedEdges->DE];
doGP=doLGP=doTP =doGP3D=False;doSSS=True;
If[MemberQ[NM,All,{0,\[Infinity]}],doGP=doLGP=doTP=doGP3D=True];
If[MemberQ[NM,GraphPlot,{0,\[Infinity]}],doGP=True];
If[MemberQ[NM,LayeredGraphPlot,{0,\[Infinity]}],doLGP=True];
If[MemberQ[NM,TreePlot,{0,\[Infinity]}],doTP=True];
If[MemberQ[NM,GraphPlot3D,{0,\[Infinity]}],doGP3D=True];
If[MemberQ[NM,NoSSS,{0,\[Infinity]}],doSSS=False];
If[sss["Verdict"]=="Dead",doGP=doLGP=doTP=doGP3D=False];
cellsToHighlight=Flatten[MapIndexed[{#1,#2[[1]]}&,Reverse@(sss["CellsDeleted"][[Max[start,sssmn];;Min[sssmx,Length[sss["Evolution"]]]-1]]),{2}],1];
rulesApplied=Reverse@(sss["RulesUsed"][[Max[start,sssmn];;Min[sssmx,Length[sss["Evolution"]]]-1]]);
ans = 
ArrayPlot[(FromAlpha/@ (sss["Evolution"][[Max[start,sssmn];;Min[sssmx,Length[sss["Evolution"]]]]])),myColorOptions[sss["MaxColor"]],Mesh->mesh,ImageSize->SS,
Epilog->Switch[HlM,
Dot,Disk[#+0.5{-1,1},.18]& /@ cellsToHighlight,
Frame,{EdgeForm[Thick],FaceForm[],Rectangle[#-{1,0}]& /@ cellsToHighlight},
Number,Text @@@ (cellsToHighlight /. {x_Integer,y_Integer}:>{rulesApplied[[y]],{x,y}+.5{-1,1}}),
_,{}]
];
Row[Flatten@{
If[!doSSS,{},Pane[
Switch[RP,
Right, Grid[{{ans,SSSRuleIcon[sss["RuleSet"],sss["MaxColor"],ImageSize->IcS]}}],
Left, Grid[{{SSSRuleIcon[sss["RuleSet"],sss["MaxColor"],ImageSize->IcS],ans}}], 
Bottom|True, Grid[{{ans},{SSSRuleIcon[sss["RuleSet"],sss["MaxColor"],ImageSize->IcS]}}], 
Top,  Grid[{{SSSRuleIcon[sss["RuleSet"],sss["MaxColor"],ImageSize->IcS]},{ans}}], 
_,ans],ImageSize->ImS,ImageSizeAction->"ShrinkToFit"]],
If[doGP,GraphPlot[grph,GraphLayout->"SpringElectricalEmbedding",
Sequence@@Flatten[{ImageSize->NS,FilterRules[{opts}, Options[GraphPlot]],
VertexSize->Large,VertexLabels->Placed[Automatic,Center]}]],{}],
If[doLGP,LayeredGraphPlot[grph,Sequence@@Flatten[{ImageSize->NS,FilterRules[{opts}, Options[LayeredGraphPlot]],VertexSize->Large,VertexLabels->Placed[Automatic,Center]}]],{}],
If[doTP,TreePlot[grph,Top,1,Sequence@@Flatten[{ImageSize->NS,FilterRules[{opts}, Options[TreePlot]],VertexSize->Large,VertexLabels->Placed[Automatic,Center],DirectedEdges->True}]],{}],
If[doGP3D,GraphPlot3D[grph,GraphLayout->"SpringElectricalEmbedding",Sequence@@Flatten[{ImageSize->NS,FilterRules[{opts}, Options[GraphPlot3D]],VertexSize->Large,VertexLabels->Placed[Automatic,Center]}]],{}]
},"  "]];
SSS[rs:{___Rule},init_String,n_Integer?Positive,opts:OptionsPattern[]] := Module[{sss},
sss=SSSInitialize[rs,init,Mode->Silent];
If[sss["Verdict"]=!="Dead", 
sss=SSSEvolve[sss,n-1,Sequence@@FilterRules[{opts},Options[SSSEvolve]]]; 
If[OptionValue[Mode]=!=Silent, Print@SSSDisplay[sss,Sequence@@FilterRules[{opts},Options[SSSDisplay]]]];
];
sss
];
SSS[rs:{___Rule},n_Integer?Positive,opts___] := SSS[rs,SSSInitialState[rs],n,opts];
SSS[rs_Integer,n_Integer,opts___] := SSS[FromReducedRankIndex[rs],n,opts];
SSS[<|"Index"->_,"QCode"->_,"RuleSet"->rs_|>, x___] := SSS[rs,x];
Options[SSS]=Join[{Mode->Loud},Options[SSSEvolve],Options[SSSDisplay]];
SyntaxInformation[SSS]={"ArgumentsPattern"->{_,_,_,OptionsPattern[]}};
(*
SyntaxInformation[SSS]={"ArgumentsPattern"->{((_Association)|(___Rule)),___String,___Integer?Positive,OptionsPattern[]}};
*)
dynamicLabel[lbl_,max_]:=Dynamic[If[Clock[{1,max,1},max]==lbl,Framed[lbl,Background->Green,RoundingRadius->Scaled[.5]],lbl]];
SetAttributes[SSSInteractiveDisplay, HoldFirst];
SSSInteractiveDisplay[sss_] := With[{mxmx=Max[List @@@ Evaluate[sss]["Net"]]},
Manipulate[
If[Head[vl]===List,vp=Automatic];
If[mx<mn,mx=mn+1];
If[sssmx<sssmn,sssmx=sssmn+1];
If[ntmx<ntmn,ntmx=ntmn+1];
args={Min->mn,Max->mx,SSSMin->(sssmn/. 0->Automatic),SSSMax->(sssmx/. mxmx+1->Automatic),NetMin->(ntmn/. 0->Automatic),NetMax->(ntmx/.mxmx+1->Automatic),HighlightMethod->hlm,RulePlacement->sr,NetMethod->Flatten[{nm,If[no,{NoSSS},{}]}],ImageSize->is,NetSize->{Automatic,ns},SSSSize->{Automatic,ssss},IconSize->{Automatic,cns},VertexSize->vs,
VertexLabels->If[vp===Automatic,vl,Placed[vl,vp]],
DirectedEdges->dir};
SSSDisplay[Evaluate[sss],Flatten[args,1]],
Grid[{{
Control[{{hlm,Number,"HighlightMethod"},{Dot,Frame,Number,None}}],
Control[{{sr,Bottom,"RulePlacement"},{Bottom,Top,Left,Right,None}}],
Control[{{nm,GraphPlot,"NetMethod"},{GraphPlot,LayeredGraphPlot,TreePlot,GraphPlot3D,All}}],
Button["Use options",
CellPrint[ExpressionCell[Defer[SSSDisplay][Defer[sss],Evaluate[Sequence@@args]],"Input"]];
SelectionMove[InputNotebook[],Previous,Cell];
],
Button["Use as default",
CellPrint[ExpressionCell[Defer[SetOptions][Defer[SSSDisplay],Evaluate[Sequence@@args]],"Input"]];
SelectionMove[InputNotebook[],Previous,Cell];
]
}},Spacings->1],
{args,{},ControlType->None},
Grid[{{Control[{{mn,1,"Min"},1,mxmx,1,Appearance->"Labeled"}],Control[{{mx,mxmx,"Max"},1,mxmx,1,Appearance->"Labeled"}],
Row[{
Control[{{dir,False,"directed"},{False,True}}],"    ",
Control[{{no,False,"NoSSS"},{False,True}}]
}]
},
{Control[{{sssmn,0,"SSSMin"},0,mxmx,1,Appearance->"Labeled"}],Control[{{sssmx,mxmx+1,"SSSMax"},0,mxmx+1,1,Appearance->"Labeled"}],"(a NetMethod option)"},{Control[{{ntmn,0,"NetMin"},0,mxmx,1,Appearance->"Labeled"}],Control[{{ntmx,mxmx+1,"NetMax"},0,mxmx+1,1,Appearance->"Labeled"}],
Control[{{vs,Automatic,"VertexSize ->"},{Automatic,Tiny,Small,Medium,Large,0.8->"Huge"},ControlType->PopupMenu}]
},
{Control[{{ssss,220,"SSSSize"},10,500,Appearance->"Labeled"}],
Control[{{is,350,"ImageSize"},10,500,Appearance->"Labeled"}],Control[{{vl,Automatic,"VertexLabels ->"},{Automatic,None,"Name","VertexWeight",
((#->Placed[#,Center,Function[{arg},dynamicLabel[arg,ntmx]]])&/@Range[ntmn+1,ntmx-1])->"Dynamic"},ControlType->PopupMenu}]},
{Control[{{cns,20,"IconSize"},10,50,Appearance->"Labeled"}],Control[{{ns,300,"NetSize"},10,800,Appearance->"Labeled"}],
Control[{{vp,Automatic,"Placed"},
{Automatic,Center,Before,After,Below,Above,Tooltip,StatusArea}}]}
},Alignment->Right,Spacings->2]
]];
SSSAnimate[sss_Association, opts:OptionsPattern[{VertexLabels->"Name",SSSDisplay}]] := Module[{g,mn,mx,VL},
{VL,mn,mx}=If[FreeQ[OptionValue[VertexLabels],"VertexWeight"],
{Placed["Name",Center],1,Length[sss["Evolution"]]},
{Placed["VertexWeight",Center],0,Max[sss["Distance"]]}];
g= SSSDisplay[sss,VertexLabels->VL (* override *),opts,
(* defaults: *) NetSize->600,NetMethod->{GraphPlot,NoSSS},VertexSize->Automatic,DirectedEdges->False];
Animate[g /. {
{Disk[__],Text[n,{x_,y_},BaseStyle->"Graphics"] }:> Text[Framed[n,List[Rule[Background,Green],Rule[FrameStyle,Black],Rule[FrameMargins,Automatic]],RoundingRadius->10],
{x,y},BaseStyle->"Graphics"],
{Disk[__],Text[m:Except[n,_Integer],{x_,y_},BaseStyle->"Graphics"] }:>Point[{x,y}]
},
{n,mn,mx,1,Appearance->"Labeled",AnimationRate->2,AnimationRunning->True}]];
nextLyndon[k_,n_,w_List] := Module[{x=Table[0,{n}],l=Length[w],lastchar=n},
x=w[[Mod[Range[1,n],l,1]]];   (* permute the digits appropriately *)
While[lastchar>=0 && x[[lastchar]]==k-1,lastchar--];  (* back up past end trash *)
If[lastchar==0,
{}, (* nothing left, we're done *)
x[[lastchar]]++;x[[;;lastchar]]  (* increment last digit, return appropriate part *)
]];
deBruijn[k_,n_] := deBruijn[k,n]=Module[{s,d=Divisors[n]},
s=NestWhileList[nextLyndon[k,n,#]&,{0},#!={}&];
Join @@ Select[s,MemberQ[d,Length[#]]&]
];
SSSInitialState[r_Rule] := Module[{lhs,k,n,chars,s,len},
lhs=First[r];
If[lhs=="",lhs="A"];
chars=Union[Characters [lhs]];
k=Length[chars];
n=StringLength[lhs];
s=deBruijn[k,n][[Mod[Range[k^n+n-1],k^n,1]]];
StringJoin[s /. Thread[Range[k]-1->chars]]
];
SSSInitialState[rs:{Rule[_,_]...}] := Module[{lhs=First /@ rs,runs,bigruns,full=StringJoin[Union[SSSInitialState /@ rs]],dels},
runs = Union[Flatten[StringJoin /@ Split[Characters[#]]& /@ lhs]]; (* runs of same character existing in lhs *)
bigruns=Last /@ SplitBy[runs,StringTake[#,1]&]; (* biggest run of each character *)
dels=StringJoin[#,StringTake[#,1]]& /@ bigruns; (* next bigger for each character *)
FixedPoint[StringReplace[#,Thread[dels->bigruns]]&,full]  (* keep replacing the too big runs by the max allowed size, stop when no futher change *)
];

(* RSS enumeration code *)
FromReducedRankIndex[i_Integer/;i>0] := Module[{n,j,quinaryDigits,quinaryCode,numberOfEOS,chopPos,extra, ans={{1}},strings,ruleset},
n=Floor[Log[5,4i-3]];
j=i-(5^n+3)/4;
quinaryDigits=IntegerDigits[j,5,n];  (* the base-5 code for this ruleset will contain n digits, the ruleset weight is n+1 *)
quinaryCode=StringJoin @@ (ToString/@quinaryDigits);
Scan[
Switch[#,
0 ,ans=Join[ans,{{},{},{1}}] ,
1,ans=Join[ans,{{},{1}}] ,
2,AppendTo[ans,{1}],
3,AppendTo[ans[[-1]],1],
4,ans[[-1]][[-1]]++
]&,
(* Print@quinaryDigits; *)
quinaryDigits];
strings=StringJoin @@@ (FromCharacterWeights /@ ans);
If[OddQ[Length[strings]],strings=AppendTo[strings,""]];
<|"Index"->i,"QCode"->quinaryCode,"RuleSet"->Rule @@@ Partition[strings,2,2]|>
];
FromReducedRankRuleSet[rs_List] := Module[{rl,wl,w,code=""},
rl=Flatten[List @@@ rs];
If[Last[rl]=="",rl=Most[rl]]; (* drop ultimate empty string, if needed *)
(* wl=1+FromAlpha /@ rl; *)
wl=ToCharacterWeights /@ rl; (* to lists of lists of numbers "A"->1, etc., but ""->{}, not 0 *)
wl=wl /. 0->{};
w=Total[Flatten[wl]]; (* weight of this rule set *)
While[wl!={{1}},
Which[
wl[[-1]][[-1]]>1, code="4"<>code; wl[[-1]][[-1]]--,
wl[[-1]][[-1]]==1 && Length[wl[[-1]]]>1,  code="3"<>code; wl[[-1]]=Most[wl[[-1]]],
Length[wl]>=3 && wl[[-3;;]]=={{},{},{1}}, code="0"<>code; wl=Drop[wl,-3],
Length[wl]>=2 && wl[[-2;;]]=={{},{1}}, code="1"<>code; wl=Drop[wl,-2],
wl[[-1]]=={1},  code="2"<>code; wl=Drop[wl,-1]
]
];
<|"Index"->(FromDigits[code,5]+(5^(w-1)+3)/4),"QCode"->code,"RuleSet"->rs|>
(* To find the index, add number of rulesets of smaller weights to reconstructed quinary code *)
];
FromReducedRankQuinaryCode[s_String]:=Module[{n,j,quinaryDigits,w,numberOfEOS,chopPos,extra,ans={{1}},strings,ruleset},quinaryDigits=ToCharacterCode[s]-48;
w=Length[quinaryDigits]+1;  (* weight of 0-length q-code is 1, each q-digit adds 1 to the weight *)
Scan[
Switch[#,
0,ans=Join[ans,{{},{},{1}}],
1,ans=Join[ans,{{},{1}}],
2,AppendTo[ans,{1}],
3,AppendTo[ans[[-1]],1],
4,ans[[-1]][[-1]]++]&,quinaryDigits];
strings=StringJoin@@@(FromCharacterWeights/@ans);
If[OddQ[Length[strings]],strings=AppendTo[strings,""]];
<|"Index"->(FromDigits[s,5]+(5^(w-1)+3)/4),"QCode"->s,"RuleSet"->Rule@@@Partition[strings,2,2]|>
(* To find the index, add number of rulesets of smaller weights to reconstructed quinary code *)
];
ToCanonical[rs_List]:=Module[{unsortedchars,alphabetizedchars,reprules},
unsortedchars=DeleteDuplicates[Flatten[Characters/@Flatten[rs,\[Infinity],Rule]]];
alphabetizedchars=Characters[FromCharacterWeights[Range[Length[unsortedchars]]]];
reprules=Thread[unsortedchars->alphabetizedchars];
Map[StringReplace[#,reprules]&,rs,{2}]];
ToCanonical[<|"Index"->_,"QCode"->_,"RuleSet"->rs_|>]:=FromReducedRankRuleSet@ToCanonical@rs;
ToLeastWeight[rs_List] := Module[{weightsortedchars,alphabetizedchars,reprules},
weightsortedchars = First /@ Sort[Tally[Flatten[Characters /@ Flatten[rs,\[Infinity],Rule]]],Last[#1]>=Last[#2]&];
alphabetizedchars = Characters[FromCharacterWeights[Range[Length[weightsortedchars]]]];
reprules=Thread[weightsortedchars->alphabetizedchars];
Map[StringReplace[#,reprules]&,rs,{2}]
];
ToLeastWeight[<|"Index"->_,"QCode"->_,"RuleSet"->rs_|>]:=FromReducedRankRuleSet@ToLeastWeight@rs;
(* TESTS PORTION *)
(* ----------------------------------------------- *)
TestForConflictingRules[<|"Index"->index_,"QCode"->qcode_,"RuleSet"->rs_|>]:=Module[{lhs,max,j,tailweight,newrs,poslist,matchstart,matchend,newqcode},
lhs=First/@rs;
max=Length[lhs];
(* first check for non-final creation rules *)
For[j=2,j<max,j++,
If[StringLength[lhs[[j]]]==0, (* found first case, if any! *)
tailweight=RuleSetWeight[rs[[j+1;;]]]; (* weight after creation rule *)
If[tailweight==0,Return[FromReducedRankIndex[index+1]]]; (* shouldn't happen, creation rule isn't last, since j<max *)
newrs=Append[rs[[;;j-1]], ""->rs[[j,2]]<>(StringJoin @@ Table["A",{tailweight}])];
Return[FromReducedRankRuleSet[newrs]] (* We're outta here *)
]
];
(* now check for other conflicting rules cases *)
j=2;
While[j<=max,  (* j starts at 2 and counts up, look for conflicts in earlier rules *)
If[Length[poslist=StringPosition[lhs[[j]],lhs[[;;j-1]]]]>0,  (* we have a conflicting rules case *)
{matchstart,matchend}=First[Sort[poslist,Last[#1]<Last[#2]&]];  (* take the earliest ending match in the string, note where it ends *)
tailweight=RuleSetWeight[Prepend[rs[[j+1;;]],StringDrop[rs[[j,1]],matchend]->rs[[j,2]]]];
If[tailweight==0,Return[FromReducedRankIndex[index+1]]];  (* skip this ruleset, go on *)
(* else *)
newqcode= StringDrop[qcode,-tailweight]<>"4"<>(StringJoin@@Table["0",{tailweight-1}]);
Return[FromReducedRankQuinaryCode[newqcode]] 
];
j++
];
{}]; (*return empty set if we got this far -- there are no conflicting rules*)
TestForNonSoloIdentityRule[arg:<|"Index"->_,"QCode"->_,"RuleSet"->rs_|>] := If[Length[rs]==1,{},TestForIdentityRule[arg]];
TestForIdentityRule[<|"Index"->index_,"QCode"->qcode_,"RuleSet"->rs_|>] := Module[{poslist,rulenum,tailweight,newqcode},
poslist=Flatten@Position[Equal @@@rs,True];
If[Length[poslist]==0,Return[{}]];                                  (* no identity rules *)
rulenum=First[poslist];
tailweight=RuleSetWeight[rs[[rulenum+1;;]]];
If[tailweight==0,Return[FromReducedRankIndex[index+1]]];  (* skip this ruleset, go on *)
If[StringLength[rs[[rulenum,1]]]==0 (* nothing to nothing rule *),
newqcode=StringDrop[qcode,-tailweight]<>"1"<>(StringJoin@@Table["0",{tailweight-1}]),
newqcode=StringDrop[qcode,-tailweight]<>"3"<>(StringJoin@@Table["0",{tailweight-1}])
];
Return[FromReducedRankQuinaryCode[newqcode]] 
];
TestForRenamedRuleSet[<|"Index"->_,"QCode"->qcode_,"RuleSet"->rs_|>] := Module[{rsn,maxChar=0,tailweight,newqcode},
rsn=Flatten[ToCharacterWeights /@ Flatten[rs/. Rule->List]];  (* transliterate rs characters as a list of positive integers *)
For[i=1,i<=Length[rsn],i++,
Switch[Sign[#-(maxChar+1)],
0,maxChar++, (* this is the next higher character, inc maxChar *)
1, i;Break[]   (* this is a bad character, note position and break out *)
]& [rsn[[i]]]
];
If[i>Length[rsn],Return[{}],tailweight=Plus@@rsn[[i+1;;]]];
newqcode= StringDrop[qcode,-tailweight]<>(StringJoin@@Table["4",{tailweight}]); (* last problem *)
FromReducedRankIndex[1+(FromReducedRankQuinaryCode[newqcode])["Index"]]  (* last prob + 1 *)
];
TestForNonSoloInitialSubstringRule[arg:<|"Index"->_,"QCode"->_,"RuleSet"->rs_|>] := If[Length[rs]==1,{},TestForInitialSubstringRule[arg]];
TestForInitialSubstringRule[<|"Index"->index_,"QCode"->qcode_,"RuleSet"->rs_|>] := 
Module[{poslist,duppos,tailweight,newqcode},
poslist=StringPosition[rs[[1,2]],rs[[1,1]]];
(* test for initial substring rule including initial identity rule! *)
If[Length[Flatten[poslist]]==0, Return[{}]];    (* no initial substring rule, quit *)
duppos=Last@First@poslist;  (* end of first match *)
tailweight=RuleSetWeight[Flatten[{StringDrop[rs[[1,2]],duppos],rs[[2;;]]}]];
(* include the rest of rhs of rule 1 in tailweight *)
If[tailweight==0,Return[FromReducedRankIndex[index+1]]];  (* skip this ruleset, go on *)
newqcode=StringDrop[qcode,-tailweight]<>"4"<>(StringJoin@@Table["0",{tailweight-1}]); 
FromReducedRankQuinaryCode[newqcode]
];
TestForShorteningRuleSet[<|"Index"->index_,"QCode"->_,"RuleSet"->rs_|>] := Module[{ruletypes=Union[Sign[Map[StringLength,rs,{2}] /. Rule->Subtract]]},
Return[If[MemberQ[ruletypes,1] && FreeQ[ruletypes,-1],FromReducedRankIndex[index+1],{}]]];
(* At least one shortening rule and no lengthening rules *)
TestForUnbalancedRuleSet[<|"Index"->index_,"QCode"->_,"RuleSet"->rs_|>] :=
If[(Union[Flatten[Characters /@ First /@ rs] ] != Union[Flatten[Characters /@ Last /@ rs]]),
FromReducedRankIndex[index+1],
{}];
TestForAll[rs:<|"Index"->_,"QCode"->_,"RuleSet"->_|>] := Module[{ans}, 
If[Length[ans=TestForConflictingRules[rs]]>0,Return[ans]];
If[Length[ans=TestForNonSoloIdentityRule[rs]]>0,Return[ans]];
If[Length[ans=TestForRenamedRuleSet[rs]]>0,Return[ans]];
If[Length[ans=TestForNonSoloInitialSubstringRule[rs]]>0,Return[ans]];
If[Length[ans=TestForUnbalancedRuleSet[rs]]>0,Return[ans]];
Return[TestForShorteningRuleSet[rs]]
]; 
(* Code to display and evaluate/expand normal and indexed concatenation *)

Concatenate[l__List] := Join[l];
Format[Concatenate[l__]] := Row[Riffle[{l}, "⧺"]];  (* FromCharacterCode[10746] *) 

(* Formatting for IndexedConcatenate *)
Clear[IndexedConcatenate];
Format[IndexedConcatenate[x__, {var_, start_, finish_}]] := 
  DisplayForm[RowBox[{UnderoverscriptBox["\[Euro]", RowBox[{var, "\[DoubleRightTee]", start}], finish], "[", Sequence @@ Riffle[{x}, ","], "]"}]]; 
Format[IndexedConcatenate[x__, {var_, finish_}]] :=  DisplayForm[RowBox[{UnderoverscriptBox["\[Euro]", var, finish], "[", Sequence @@ Riffle[{x}, ","], "]"}]];
Format[IndexedConcatenate[x__, finish_]] := DisplayForm[RowBox[{OverscriptBox["\[Euro]", finish], "[", Sequence @@ Riffle[{x}, ","], "]"}]];

(* Expansion Logic *)
iC[x__, iter:(_Integer|{_,_Integer}|{_,_Integer,_Integer})] := Sequence @@ (Join @@ Table[{x}, iter]); 
iC[x__] := IndexedConcatenate[x];

(* define a safe custom expander rather than overriding system Expand *)
SSSExpand[x_] := (x //. IndexedConcatenate -> iC);

(* Code to convert a network to/from its specification *)
ToNetDifferenceSets::usage = "ToNetDifferenceSets[net] converts network rules to difference sets.";
FromNetDifferenceSets::usage = "FromNetDifferenceSets[l] converts difference sets back to network rules.";
ToNetDifferenceSets[net:{__Rule}] := Module[{nodediffpairs},
  nodediffpairs = {#[[1]], #[[2]] - #[[1]]} & /@ net;
  Rest /@ Map[Last, Gather[Join[{#, 0} & /@ Range[Max[First /@ nodediffpairs]], nodediffpairs], First[#1] == First[#2] &], {2}]
];
FromNetDifferenceSets[diffs:{__List}] := Flatten[MapIndexed[Rule[First[#2], First[#2] + #1] &, diffs, {2}]];

(* Code to (attempt to) reduce lists to (nested) indexed concatenations *)
ReduceSetList::usage = "ReduceSetList[l] summarizes duplicate subsequences using IndexedConcatenate.";

(* START PRIVATE CONTEXT - Critical for stability *)
Begin["`Private`"] 

$debug = False;

FindSeqFns[repLen_Integer, varName_, subseqList_List] := Module[{parted, firstRep, numArray, fnList, ans},
   parted = Partition[subseqList, repLen];
   firstRep = First@parted;
   numArray = Transpose[Cases[#, _Integer, Infinity] & /@ parted];
   
   (* Protect against FindSequenceFunction failures *)
   fnList = Quiet[FindSequenceFunction[#, varName] & /@ numArray];
   
   (* If FindSequenceFunction returns the list itself, it failed to find a pattern *)
   If[MemberQ[fnList, _List], Return[subseqList]];

   ans = {IndexedConcatenate[Sequence @@ ReplacePart[firstRep, Thread[Position[firstRep, _Integer] -> fnList]], {varName, 1, Length[subseqList]/repLen}]};
   
   (* Verify the reduction is valid *)
   If[SSSExpand[ans] === SSSExpand[subseqList], ans, subseqList]
];

improveReduction[l_List] := Module[{l1 = l, l0 = l, p},
   If[Length[l] <= 1, Return[l]];
   
   p = Flatten@Position[l0, IndexedConcatenate[__, {__}], {1}];
   
   While[Length[p] > 0 && Length[l0] > 1,
      l1 = improveReductionAt[First[p], l0];
      If[l1 === l0,
         p = Rest[p], (* Try next position *)
         l0 = l1; 
         p = Flatten@Position[l0, IndexedConcatenate[__, {__}], {1}]; (* Restart scan *)
      ];
   ];
   l1
];

improveReductionAt[k_Integer, l_List] := Module[{
    wholeL, leftL, midEl, rightL, leftLNew, midElNew, rightLNew, leftEltsToDrop, 
    temp, countRolled = 0, rollLen, oldArgList, newArgList, iter, iterVar, iterStart, iterStop
    },
   If[k < 1 || k > Length[l], Return[l]]; 
   
   wholeL = SSSExpand@l;
   leftL = Take[l, k - 1];
   midEl = l[[k]];
   rightL = Drop[l, k];
   
   If[Head[midEl] =!= IndexedConcatenate, Return[l]];
   
   (* Logic to 'roll' the loop to include previous elements *)
   oldArgList = Most[List @@ midEl];
   iter = Last[List @@ midEl];
   If[Length[iter] == 2, iterStart = 1, iterStart = iter[[2]]];
   iterVar = First[iter];
   iterStop = Last[iter];

   While[True,
      If[Length[leftL] == 0, Break[]];
      leftLNew = leftL;
      
      newArgList = RotateRight[oldArgList];
      newArgList = ReplacePart[newArgList, 1 -> (newArgList[[1]] /. iter[[1]] -> iter[[1]] - 1)];
      newArgList = FullSimplify[newArgList];
      
      leftEltsToDrop = SSSExpand@{First[newArgList] /. iterVar -> iterStart};
      
      (* Check if we can absorb the element to the left *)
      While[Length[leftEltsToDrop] > 0 && Length[leftLNew] > 0 && 
            Length[(temp = {SSSExpand[Last[leftLNew]]})] <= Length[leftEltsToDrop],
          leftLNew = Most[leftLNew];
          leftEltsToDrop = Drop[leftEltsToDrop, -Length[temp]];
      ];
      
      midElNew = IndexedConcatenate[Sequence @@ newArgList, iter];
      rightLNew = Prepend[rightL, (Last[oldArgList] /. iterVar -> iterStop)];
      
      (* Verification *)
      If[wholeL === SSSExpand[Join[leftLNew, {midElNew}, rightLNew]],
          countRolled++;
          leftL = leftLNew;
          midEl = midElNew;
          rightL = rightLNew,
          Break[] (* Roll failed *)
      ];
   ];
   
   (* Logic to absorb elements to the right *)
   midElNew = midEl; 
   rightLNew = rightL;
   newArgList = oldArgList = Most[List @@ midEl];
   
   If[countRolled >= (rollLen = Length[newArgList]),
       iterStop += Quotient[countRolled, rollLen];
       midElNew = IndexedConcatenate[Sequence @@ newArgList, {iterVar, iterStart, iterStop}];
       rightLNew = Drop[rightLNew, rollLen * Quotient[countRolled, rollLen]];
       countRolled -= rollLen * Quotient[countRolled, rollLen];
   ];

   (* Merge neighboring IndexedConcatenates if possible *)
   rightLNew = SequenceReplace[rightLNew, {IndexedConcatenate[a_, iter1_], IndexedConcatenate[a_, iter2_]} :> 
     Which[
       Head[iter1] === Head[iter2] === Integer, List@IndexedConcatenate[a, iter1 + iter2],
       True, {IndexedConcatenate[a, iter1], IndexedConcatenate[a, iter2]}
     ]
   ];

   Join[leftL, {midElNew}, rightLNew]
];

ReduceSetList[l_List] := Module[{l1, l0 = l, gl0, repLen, pos, varName, len, patterns, pVars},
   If[Length[l] <= 1, Return[l]];
   
   (* 1. Exact Subsequence Matching *)
   len = Length[l0];
   l1 = SequenceReplace[l0, {x : Repeated[a_, {2, len}]} :> IndexedConcatenate[a, Length[{x}]]];
   
   If[l1 =!= l0,
      l1 = improveReduction[l1];
      Return[ReduceSetList[l1]];
   ];
   
   (* 2. Structural/Generic Pattern Matching *)
   repLen = 1;
   
   (* Limit loop to prevent hangs on complex lists *)
   While[2 * repLen <= Length[l1] && repLen < 20, 
      
      (* Normalize list to find structural repetition (generic pattern) *)
      gl0 = (l0 /. (i_Integer /; i != 1) -> 0);
      
      (* Construct a safe pattern for "Any sequence of length repLen repeated" *)
      pVars = Table[Unique["p"], {repLen}];
      patterns = Pattern[#, Blank[]] & /@ pVars;
      
      pos = SequencePosition[gl0, {Repeated[PatternSequence @@ patterns, {2, Infinity}]}, Overlaps -> False];
      
      If[Length[pos] > 0,
          (* Find a variable name not used in the list *)
          Do[varName = ToExpression["n$" <> ToString[i]]; If[FreeQ[l0, varName], Break[]], {i, 1, 1000}];
          
          l1 = Flatten[SequenceSplit[l0, Thread[(Take[l0, #] & /@ pos) -> (FindSeqFns[repLen, varName, Take[l0, #]] & /@ pos)]], 1];
          
          If[l1 =!= l0,
             l1 = improveReduction[l1];
             Return[ReduceSetList[l1]]; (* Recurse if we found something *)
          ];
      ];
      repLen++;
   ];

   l1
];

End[] (* End Private Context *)
EndPackage[]