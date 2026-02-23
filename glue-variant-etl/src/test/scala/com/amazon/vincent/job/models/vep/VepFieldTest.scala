// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models.vep

import com.amazon.vincent.job.VincentTestSuite
import com.amazon.vincent.job.models.exceptions.VincentUserException
import com.amazon.vincent.job.models.vep.VepDefaultField.{
  Allele,
  AminoAcids,
  Biotype,
  CdnaPosition,
  CdsPosition,
  Codons,
  Consequence,
  Distance,
  ExistingVariation,
  Exon,
  Feature,
  FeatureType,
  Flags,
  Gene,
  HgncId,
  Hgvsc,
  Hgvsp,
  Impact,
  Intron,
  ProteinPosition,
  Strand,
  Symbol,
  SymbolSource
}
import org.junit.runner.RunWith
import org.scalatest.BeforeAndAfterEach
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class VepFieldTest extends AnyFunSuite with VincentTestSuite with BeforeAndAfterEach {

  test("VepDefaultFields have the correct name") {
    assertResult("Allele")(VepDefaultField.Allele.name)
    assertResult("Consequence")(VepDefaultField.Consequence.name)
    assertResult("IMPACT")(VepDefaultField.Impact.name)
    assertResult("SYMBOL")(VepDefaultField.Symbol.name)
    assertResult("Gene")(VepDefaultField.Gene.name)
    assertResult("Feature_type")(VepDefaultField.FeatureType.name)
    assertResult("Feature")(VepDefaultField.Feature.name)
    assertResult("BIOTYPE")(VepDefaultField.Biotype.name)
    assertResult("EXON")(VepDefaultField.Exon.name)
    assertResult("INTRON")(VepDefaultField.Intron.name)
    assertResult("HGVSc")(VepDefaultField.Hgvsc.name)
    assertResult("HGVSp")(VepDefaultField.Hgvsp.name)
    assertResult("cDNA_position")(VepDefaultField.CdnaPosition.name)
    assertResult("CDS_position")(VepDefaultField.CdsPosition.name)
    assertResult("Protein_position")(VepDefaultField.ProteinPosition.name)
    assertResult("Amino_acids")(VepDefaultField.AminoAcids.name)
    assertResult("Codons")(VepDefaultField.Codons.name)
    assertResult("Existing_variation")(VepDefaultField.ExistingVariation.name)
    assertResult("DISTANCE")(VepDefaultField.Distance.name)
    assertResult("STRAND")(VepDefaultField.Strand.name)
    assertResult("FLAGS")(VepDefaultField.Flags.name)
    assertResult("SYMBOL_SOURCE")(VepDefaultField.SymbolSource.name)
    assertResult("HGNC_ID")(VepDefaultField.HgncId.name)
  }

  test("Return all values") {
    assertResult(
      Seq(
        Allele,
        Consequence,
        Impact,
        Symbol,
        Gene,
        FeatureType,
        Feature,
        Biotype,
        Exon,
        Intron,
        Hgvsc,
        Hgvsp,
        CdnaPosition,
        CdsPosition,
        ProteinPosition,
        AminoAcids,
        Codons,
        ExistingVariation,
        Distance,
        Strand,
        Flags,
        SymbolSource,
        HgncId))(VepDefaultField.values)
  }

  test("Get field from name") {
    assertResult(Some(VepDefaultField.Allele))(VepDefaultField.fromName("Allele"))
    assertResult(Some(VepDefaultField.Consequence))(VepDefaultField.fromName("Consequence"))
    assertResult(Some(VepDefaultField.Impact))(VepDefaultField.fromName("IMPACT"))
    assertResult(Some(VepDefaultField.Symbol))(VepDefaultField.fromName("SYMBOL"))
    assertResult(Some(VepDefaultField.Gene))(VepDefaultField.fromName("Gene"))
    assertResult(Some(VepDefaultField.FeatureType))(VepDefaultField.fromName("Feature_type"))
    assertResult(Some(VepDefaultField.Feature))(VepDefaultField.fromName("Feature"))
    assertResult(Some(VepDefaultField.Biotype))(VepDefaultField.fromName("BIOTYPE"))
    assertResult(Some(VepDefaultField.Exon))(VepDefaultField.fromName("EXON"))
    assertResult(Some(VepDefaultField.Intron))(VepDefaultField.fromName("INTRON"))
    assertResult(Some(VepDefaultField.Hgvsc))(VepDefaultField.fromName("HGVSc"))
    assertResult(Some(VepDefaultField.Hgvsp))(VepDefaultField.fromName("HGVSp"))
    assertResult(Some(VepDefaultField.CdnaPosition))(VepDefaultField.fromName("cDNA_position"))
    assertResult(Some(VepDefaultField.CdsPosition))(VepDefaultField.fromName("CDS_position"))
    assertResult(Some(VepDefaultField.ProteinPosition))(
      VepDefaultField.fromName("Protein_position"))
    assertResult(Some(VepDefaultField.AminoAcids))(VepDefaultField.fromName("Amino_acids"))
    assertResult(Some(VepDefaultField.Codons))(VepDefaultField.fromName("Codons"))
    assertResult(Some(VepDefaultField.ExistingVariation))(
      VepDefaultField.fromName("Existing_variation"))
    assertResult(Some(VepDefaultField.Distance))(VepDefaultField.fromName("DISTANCE"))
    assertResult(Some(VepDefaultField.Strand))(VepDefaultField.fromName("STRAND"))
    assertResult(Some(VepDefaultField.Flags))(VepDefaultField.fromName("FLAGS"))
    assertResult(Some(VepDefaultField.SymbolSource))(VepDefaultField.fromName("SYMBOL_SOURCE"))
    assertResult(Some(VepDefaultField.HgncId))(VepDefaultField.fromName("HGNC_ID"))
  }

  test("Test extra fields") {
    val extraFieldA = ExtraField("EXTRA_FIELD_A")
    val extraFieldB = ExtraField("EXTRA_FIELD_B")
    assertResult("EXTRA_FIELD_A")(extraFieldA.name)
    assertResult("EXTRA_FIELD_B")(extraFieldB.name)
  }

  test("Check fromHeader return order") {
    val testVepHeader = """##INFO=<ID=CSQ,Number=.,
                                 |Type=String,Description=
                                 |"Consequence annotations from Ensembl VEP.
                                 | Format: Allele|Consequence|Format|HIGH_INF_POS|TRANSCRIPTION_FACTORS">
                                 |""".stripMargin.replaceAll("\n", "")

    val vepFields = VepFieldGenerator.fromHeader(testVepHeader)

    assertResult(
      Array(
        VepDefaultField.Allele,
        VepDefaultField.Consequence,
        ExtraField("format"),
        ExtraField("high_inf_pos"),
        ExtraField("transcription_factors")).toSeq)(vepFields.get)
  }

  test("Works even  for non CSQ headers") {
    val testVepHeader = """##INFO=<ID=vep,Number=.,
                          |Type=String,Description=
                          |"Consequence annotations from Ensembl VEP.
                          | Format: Allele|Consequence|Format|HIGH_INF_POS|TRANSCRIPTION_FACTORS">
                          |""".stripMargin.replaceAll("\n", "")

    val vepFields = VepFieldGenerator.fromHeader(testVepHeader)

    assertResult(
      Array(
        VepDefaultField.Allele,
        VepDefaultField.Consequence,
        ExtraField("format"),
        ExtraField("high_inf_pos"),
        ExtraField("transcription_factors")).toSeq)(vepFields.get)
  }

  test("No VEP headers returns None") {
    val testVepHeader = """##INFO=<ID=vep,Number=.,
                          |Type=String,Description=
                          |"This is not a Consequence annotations from Ensembl VEP.
                          | Format: Allele|Consequence|Format|HIGH_INF_POS|TRANSCRIPTION_FACTORS">
                          |""".stripMargin.replaceAll("\n", "")

    val vepFields = VepFieldGenerator.fromHeader(testVepHeader)
    assertResult(None)(vepFields)
  }

  test("Invalid info header throws VincentUserException") {
    val testVepHeader = """##INFO=<ID=vep,Number=.,
                          |Type=String,Description=
                          | Format: Allele|Consequence|Format|HIGH_INF_POS|TRANSCRIPTION_FACTORS"
                          |""".stripMargin.replaceAll("\n", "")

    val caught = intercept[VincentUserException] {
      VepFieldGenerator.fromHeader(testVepHeader)
    }
    assertResult(caught.getMessage) {
      "VCF header is malformed. Please ensure header is as per specification."
    }
  }
}
